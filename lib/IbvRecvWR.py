import random
import sys

from typing import Optional

try:
    from .IbvQPCap import IbvQPCap  # for package import
except ImportError:
    from IbvQPCap import IbvQPCap  # for direct script debugging

try:
    from .IbvSge import IbvSge  # for package import
except ImportError:
    from IbvSge import IbvSge  # for direct script debugging
try:
    from .attr import Attr
except ImportError:
    from attr import Attr

try:
    from .codegen_context import CodeGenContext  # for package import
except ImportError:
    from codegen_context import CodeGenContext  # for direct script debugging

try:
    from .utils import emit_assign  # for package import
except ImportError:
    from utils import emit_assign  # for direct script debugging

try:
    from .value import ConstantValue, EnumValue, FlagValue, IntValue, ListValue, OptionalValue, ResourceValue
except ImportError:
    from value import ConstantValue, EnumValue, FlagValue, IntValue, ListValue, OptionalValue, ResourceValue

try:
    from .contracts import State
except ImportError:
    from contracts import State


class IbvRecvWR(Attr):
    FIELD_LIST = ["wr_id", "next", "sg_list", "num_sge"]
    MUTABLE_FIELDS = FIELD_LIST

    def __init__(self, wr_id=None, next_wr=None, sg_list=None, num_sge=None):
        self.wr_id = OptionalValue(IntValue(wr_id, 0xFFFFFFFF) if wr_id is not None else None)  # 可选的wr_id
        self.next = OptionalValue(next_wr, factory=lambda: IbvRecvWR.random_mutation())  # 另一个IbvRecvWR对象或None

        # ---- helpers (e.g., in fuzz_mutate.py or a utils module) ----
        def pick_live_local_mr_name(snap: dict, rng: random.Random) -> str | None:
            # snap: { (rtype,name): "STATE" }
            cands = []
            for (rt, nm), (st, _) in (snap or {}).items():
                if rt == "mr" and st == State.ALLOCATED:
                    cands.append(nm)
            if not cands:
                return None
            return rng.choice(cands)

        def _sge_factory(snap=None, contract=None, rng=None):
            mr_name = pick_live_local_mr_name(snap, rng or random)
            if mr_name:
                return IbvSge(mr=mr_name)  # IbvSge 内部会变成 ResourceValue(resource_type="mr", value=mr_name)
            else:
                # TODO: 没可用 MR：先占位，再由更高层（mutator/repair 或 apply(ctx)）去补
                return IbvSge()

        def _sg_after(kind, lv, idx, item, snap, contract, rng, path):
            # 1) 维护 num_sge 不变式
            try:
                # 这里的 owner(=self) 可通过闭包拿到；直接写 self.num_sge 更简单：
                self.num_sge = OptionalValue(IntValue(len(lv.value), mutable=False))  # lv: ListValue
                # print(f"  [*] IbvRecvWR.sg_list after_mutate: set num_sge={len(lv.value)}")
            except Exception:
                pass

            # 似乎没有必要，mutate掉就mutate掉，这不是必须的
            # # 2) 补 mr（如果工厂没拿到或之后 mutate 掉了）
            # if isinstance(item, IbvSge):
            #     if not hasattr(item, "mr") or item.mr is None:
            #         mr_name2 = pick_live_local_mr_name(snap, rng or random)
            #         if mr_name2:
            #             item.mr = ResourceValue(value=mr_name2, resource_type="mr")

        self.sg_list = OptionalValue(
            ListValue(
                value=sg_list if sg_list is not None else [],
                factory=_sge_factory,
                on_after_mutate=_sg_after,
            )
        )

        # self.sg_list = OptionalValue(
        #     ListValue(value=sg_list, factory=lambda: IbvSge.random_mutation()) if sg_list is not None else None,
        #     factory=lambda: ListValue([], factory=lambda: IbvSge.random_mutation()),
        # )  # list[IbvSge]
        self.num_sge = OptionalValue(
            IntValue(max(num_sge, len(self.sg_list.value)), 0)
            if num_sge is not None
            else IntValue(len(self.sg_list.value) if self.sg_list else 0)
        )

    @classmethod
    def random_mutation(cls, chain_length=1, rng: Optional[random.Random] = None):
        """
        生成一个随机的 Recv WR；当 chain_length > 1 时，生成简单链表（后创建的作为前一个的 next）
        - sg_list: 0~3 个 IbvSge（mr 可能留空，由上层/回调/repair 补齐）
        - wr_id: 随机 64-bit
        - num_sge: 与 sg_list 长度一致
        """
        rng = rng or random

        def _mk_one_wr():
            k = rng.choice([0, 1, 2, 3])  # SGE 个数
            sges = [IbvSge() for _ in range(k)]  # 这里不强行填 mr，交给 ListValue 的工厂/回调或后续 repair
            return cls(
                wr_id=rng.randint(0, 2**64 - 1),
                next_wr=None,
                sg_list=sges,
                num_sge=k,
            )

        if chain_length <= 1:
            return _mk_one_wr()
        else:
            head = None
            # 生成长度为 chain_length 的单向链表：新建的作为头，指向之前的 head
            for _ in range(chain_length):
                node = _mk_one_wr()
                # 把现有 head 接到 node.next
                node.next = OptionalValue(head, factory=lambda: IbvRecvWR.random_mutation())
                head = node
            return head

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_recv_wr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        # wr_id
        if self.wr_id:
            s += emit_assign(varname, "wr_id", self.wr_id)
        # sg_list
        if self.sg_list:
            val = self.sg_list.value  # ListValue
            if len(val) > 0:
                num_sge = len(val)
                sg_list_name = f"{varname}_sg_list"
                # 生成sge数组
                if ctx:
                    sg_list_name = ctx.gen_var_name(prefix=f"{varname}_sg_list")
                    ctx.alloc_variable(f"{sg_list_name}", "struct ibv_sge", array_size=f"[{num_sge}]")
                    # print(f"  [*] IbvRecvWR.to_cxx: alloc {sg_list_name}[{num_sge}]")
                for idx, sge in enumerate(val):
                    sge_var = f"{sg_list_name}[{idx}]"
                    s += sge.to_cxx(sge_var, ctx)
                s += f"    {varname}.sg_list = {sg_list_name};\n"
        if self.num_sge:
            s += emit_assign(varname, "num_sge", self.num_sge)
        # next
        if self.next:
            next_var = varname + "_next"
            s += self.next.to_cxx(next_var, ctx)
            s += f"    {varname}.next = &{next_var};\n"
        else:
            s += f"    {varname}.next = NULL;\n"
        return s


if __name__ == "__main__":
    wr = IbvRecvWR.random_mutation(chain_length=random.randint(1, 5))
    print(wr.to_cxx("recv_wr", ctx=None))
    for i in range(1000):
        wr.mutate()
        print(wr.to_cxx(f"recv_wr_{i}", ctx=None))
        print("-----")
    # wr.mutate()

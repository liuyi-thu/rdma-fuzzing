import random

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
    from .value import ConstantValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue
except ImportError:
    from value import ConstantValue, EnumValue, FlagValue, IntValue, OptionalValue, ResourceValue

try:
    from .IbvModerateCQ import IbvModerateCQ  # for package import
except ImportError:
    from IbvModerateCQ import IbvModerateCQ


class IbvModifyCQAttr(Attr):
    FIELD_LIST = ["attr_mask", "moderate"]
    MUTABLE_FIELDS = ["attr_mask", "moderate"]
    EXPORT_FIELDS = ["attr_mask", "moderate"]

    def __init__(self, attr_mask=None, moderate=None):
        self.attr_mask = OptionalValue(
            IntValue(attr_mask) if attr_mask is not None else None, factory=lambda: IntValue(random.choice([0, 1, 3]))
        )
        # self.moderate = moderate  # IbvModerateCQ 对象
        self.moderate = OptionalValue(
            moderate if moderate is not None else None, factory=lambda: IbvModerateCQ.random_mutation()
        )

    @classmethod
    def random_mutation(cls):
        return cls(attr_mask=random.choice([0, 1, 3]), moderate=IbvModerateCQ.random_mutation())

    def to_cxx(self, varname, ctx=None):
        if ctx:
            ctx.alloc_variable(varname, "struct ibv_modify_cq_attr")
        s = f"\n    memset(&{varname}, 0, sizeof({varname}));\n"
        for field in self.FIELD_LIST:
            val = getattr(self, field)
            if not val:
                continue
            if field == "moderate":
                moderate_var = varname + "_moderate"
                s += val.to_cxx(moderate_var, ctx)
                s += f"    {varname}.moderate = {moderate_var};\n"
            else:
                s += emit_assign(varname, field, val)
        return s


if __name__ == "__main__":
    attr = IbvModifyCQAttr.random_mutation()
    print(attr.to_cxx("modify_cq_attr"))

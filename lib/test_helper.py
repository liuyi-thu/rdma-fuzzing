import random


# ---- MW alloc 的最小形态 ----
def _mk_min_alloc_mw(pd_name: str):
    from .verbs import AllocMW

    # 若你的 AllocMW 需要 mw_type，按 verbs.py 调整
    return AllocMW(pd=pd_name, mw=f"mw_{random.randrange(1 << 16)}", mw_type="IBV_MW_TYPE_1")


# ---- DM alloc 的最小形态 ----
def _mk_min_alloc_dm():
    from lib.ibv_all import IbvAllocDmAttr  # 若你的 IbvAllocDmAttr 有不同字段，按需调整

    from .verbs import AllocDM

    # 视你的 verbs.py 签名而定：很多实现是 ctx_name + length + align
    return AllocDM(
        ctx_name="ctx", dm=f"dm_{random.randrange(1 << 16)}", attr_obj=IbvAllocDmAttr(length=0x2000, log_align_req=64)
    )

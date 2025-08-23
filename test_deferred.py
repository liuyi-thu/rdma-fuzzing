from lib.ibv_all import IbvRdmaInfo, IbvSendWR, IbvSge
from lib.value import DeferredValue

sge = IbvSge(
    addr="peer0",  # should be a pair, why we change this? we can bind them ogether
    length=1024,
    lkey="peer0",
)
wr = IbvSendWR(
    opcode="IBV_WR_RDMA_WRITE",
    num_sge=1,
    sg_list=[sge],
    rdma=IbvRdmaInfo(  # 你的类里把 remote_addr/rkey 也允许 DeferredValue
        remote_addr="peer0",
        rkey="peer0",
    ),
)

print(wr.to_cxx("wr"))

AllocDM——全是整数
AllocPD——无参数
CreateCQ——整数
CreateQP——IbvQPInitAttr含有ResourceValue（cq）
CreateSRQ——整数
DeallocPD
DeregMR
DestroyCQ
DestroyQP
DestroySRQ
FreeDM
ModifyCQ——整数
ModifyQP
ModifySRQ
PollCQ——CQ only
PostRecv——含有sg_list
PostSend——含有sg_list，rdma info等
PostSRQRecv
RegMR——pd


AllocDM: dm (produced), attr_obj(IbvAllocDmAttr: length, log_align_req, comp_mask (int)), attr_var
AllocPD: pd (produced)
CreateCQ: cqe (int), cq_context (const), channel (const), comp_vector (int), cq (produced)
CreateQP: pd (required), qp (produced), init_attr_obj (IbvQPInitAttr: qp_context(const), send_cq, recv_cq (required), srq(required), cap: IbvQPCap (all int), qp_type (enum), sg_sig_all (int))
CreateSRQ: pd (required), srq (produced), srq_init_obj (IbvSrqInitAttr: srq_context (const), attr (IbvSrqAttr, all int))
DeallocPD: pd
DeregMR: mr
DestroyCQ: cq
DestroyQP: qp
DestroySRQ: srq
ModifyCQ: cq(req.), attr_obj: IbvModifyCQAttr(ints)
ModifyQP: qp(req.), attr_obj: IbvQPAttr(qp_state（可能影响FSM）, dest_qp_num（取决于对端），ah_attr(IbvAHAttr: 部分取决于对端（grh之类的，全场通用）))
ModifySRQ,
PollCQ: cq
PostRecv: qp (req.), wr_obj (IbvRecvWR: wr_id, next, sg_list(list of IbvSge), num_sge), wr_var (const)
PostSend, qp(req.), wr_obj(IbvSendWR: wr_id, next, sg_list(list of IbvSge), num_sge, rdma (对面信息)， 其他为int或者非必须), wr_var (const)
PostSRQRecv, qp (req.), wr_obj (IbvRecvWR: wr_id, next, sg_list(list of IbvSge), num_sge), wr_var (const)
RegMR, pd (req.), mr (produced.), addr (应该是个变量，可以简化为binding), length, access (int)
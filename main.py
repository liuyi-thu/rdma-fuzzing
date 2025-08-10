import copy
import json
import os
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader

from lib.codegen_context import CodeGenContext
from lib.IbvAHAttr import IbvAHAttr
from lib.IbvQPAttr import *
from lib.IbvQPInitAttr import *
from lib.IbvSendWR import *
from lib.IbvSrqAttr import *
from lib.IbvSrqInitAttr import IbvSrqInitAttr
from lib.verbs_0710_bak2 import *


def parse_trace(json_path: str, ctx: CodeGenContext) -> List[VerbCall]:
    """Read trace_output.json and convert to VerbCall list."""
    calls: List[VerbCall] = []
    with open(json_path) as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            verb = rec["verb"]
            info = rec["info"]
            ctor = VERB_FACTORY.get(verb)
            if ctor:
                calls.append(ctor(info, ctx))
    return calls


def generate_replay_code_client(buf_size):
    ctx = CodeGenContext()
    calls = [
        GetDeviceList(),  # 返回的变量固定
        OpenDevice(),  # 返回的变量固定
        FreeDeviceList(),  # 返回的变量固定
        QueryDeviceAttr(),  # 返回的变量固定
        QueryPortAttr(),  # 返回的变量固定
        QueryGID(),  # 返回的变量固定
        ReceiveMR(),  # 返回的变量固定
    ]  # 这些都是建立连接的准备
    for i in range(10):
        calls += [
            AllocPD(
                pd=f"PD{i}",
            ),
            CreateCQ(
                cq=f"CQ{i}",
            ),
            RegMR(
                pd=f"PD{i}",
                buf=f"bufs[{i}]",
                length=buf_size,
                mr=f"MR{i}",
                flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE",
            ),
            CreateQP(
                qp=f"QP{i}",
                pd=f"PD{i}",
                init_attr_obj=IbvQPInitAttr(
                    send_cq=f"CQ{i}",
                    recv_cq=f"CQ{i}",
                    cap=IbvQPCap(max_send_wr=1, max_recv_wr=1, max_send_sge=1, max_recv_sge=1),
                    qp_type="IBV_QPT_RC",
                    sq_sig_all=1,
                ),
            ),
            # 假设远端QP索引为i（这是一个假的verb，用于配对QP信息）
            ExchangeQPInfo(qp=f"QP{i}", remote_qp_index=i),
            # CreateSRQ(pd=f"PD{i}", srq=f"SRQ{i}",
            #           srq_init_obj=IbvSrqInitAttr(attr = IbvSrqAttr(max_wr=32, max_sge=1, srq_limit=0)), ),
            ModifyQP(
                qp=f"QP{i}",
                attr_mask="IBV_QP_STATE | IBV_QP_PKEY_INDEX | IBV_QP_PORT | IBV_QP_ACCESS_FLAGS",
                attr=IbvQPAttr(
                    qp_state="IBV_QPS_INIT",
                    pkey_index=0,
                    port_num=1,
                    qp_access_flags="IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE | IBV_ACCESS_LOCAL_WRITE",
                ),
            ),
            ModifyQP(
                qp=f"QP{i}",
                attr_mask="IBV_QP_STATE | IBV_QP_AV | IBV_QP_PATH_MTU | IBV_QP_DEST_QPN | IBV_QP_RQ_PSN | IBV_QP_MAX_DEST_RD_ATOMIC | IBV_QP_MIN_RNR_TIMER",
                attr=IbvQPAttr(
                    qp_state="IBV_QPS_RTR",
                    path_mtu="IBV_MTU_1024",
                    dest_qp_num=f"local_remote_qp_map[QP{i}->qp_num]",
                    rq_psn=0,
                    max_dest_rd_atomic=1,
                    min_rnr_timer=12,
                    ah_attr=IbvAHAttr(
                        is_global=1,
                        dlid="remote_info.lid",
                        sl=0,
                        src_path_bits=0,
                        port_num=1,
                        grh=IbvGlobalRoute(
                            sgid_index=1,
                            hop_limit=1,
                            traffic_class=0,
                            flow_label=0,
                            dgid=IbvGID(src_var="remote_info.gid"),
                        ),
                    ),
                ),
            ),
            ModifyQP(
                qp=f"QP{i}",
                attr_mask="IBV_QP_STATE | IBV_QP_TIMEOUT | IBV_QP_RETRY_CNT | IBV_QP_RNR_RETRY | IBV_QP_SQ_PSN | IBV_QP_MAX_QP_RD_ATOMIC",
                attr=IbvQPAttr(qp_state="IBV_QPS_RTS", timeout=14, retry_cnt=7, rnr_retry=7, sq_psn=0, max_rd_atomic=1),
            ),
            # 这里可以添加更多的操作，比如发送数据等
            PostSend(
                qp=f"QP{i}",
                wr_obj=IbvSendWR(
                    wr_id=1,
                    num_sge=1,
                    opcode="IBV_WR_SEND",
                    send_flags="IBV_SEND_SIGNALED",
                    sg_list=[IbvSge(addr=f"(uintptr_t)bufs[{i}]", length="MSG_SIZE", lkey=f"MR{i}->lkey")],
                ),
            ),
            PollCQ(cq=f"CQ{i}"),
        ]
    for i in range(10):
        calls += [
            DestroyQP(
                qp=f"QP{i}",
            ),
            DeregMR(
                mr=f"MR{i}",
            ),
            DestroyCQ(
                cq=f"CQ{i}",
            ),
            DeallocPD(
                pd=f"PD{i}",
            ),
        ]
    calls += [CloseDevice()]
    calls = test_mutate(calls, 48)  # 测试变异函数，传入calls和索引0

    for call in calls:
        if hasattr(call, "apply"):
            # call.tracker = ctx.tracker
            call.apply(ctx)

    print("All calls applied to context.")
    # print(calls)
    # print(ctx.tracker.find_dependencies('qp', 'QP0'))  # Example of finding dependencies for QP0
    body = "".join(call.generate_c(ctx) for call in calls)
    env = Environment(loader=FileSystemLoader("."))
    template = env.get_template("rdma_client_with_qp_pool.cpp.j2")
    ctx.alloc_variables_objtracker()
    variable_definitions = ctx.generate_variable_definitions_all()
    rendered = template.render(
        body=body,
        ctx="ctx",
        dev_list=ctx.dev_list,
        dev_attr=ctx.dev_attr,
        port_attr=ctx.port_attr,
        max_QPs=ctx.max_QPs,
        variable_definitions=variable_definitions,
    )
    return rendered


def test_mutate(calls: List[VerbCall], index):
    """测试变异函数"""
    ctx = CodeGenContext()
    original_calls = copy.deepcopy(calls)
    for call in original_calls:
        if hasattr(call, "apply"):
            call.apply(ctx)
        pass
    for i in range(len(original_calls)):
        print(f"Call {i}: {original_calls[i]}")

    # 首先模拟删除操作
    if hasattr(original_calls[index], "allocated_resources"):
        print(original_calls[index].allocated_resources)
        allocated_resources = original_calls[index].allocated_resources
        dependencies = []
        for res_type, res_name in allocated_resources:  # 一般来说只会有一项，还没遇到过多项的情况，暂时这么处理
            print(f"Resource type: {res_type}, Resource name: {res_name}")
            dependency = ctx.tracker.find_dependents(res_type, res_name)
            print(f"Dependencies for {res_type} {res_name}: {dependency}")
            dependencies.extend(dependency)
        print(dependencies)  # 这些资源在创建时是有依赖的，需要切换到别的地方去

        # 不对，有点乱。有一类情况是创建时用到，有一类情况是直接用到。其实是一样的，必须切换到同类其他资源上去。
        # 有个问题，需要完成整个“替换”，怎么做到呢？因为参数名各异，这又是一个很烦人的问题
        temp_ctx = CodeGenContext()
        for res_type, res_name in allocated_resources:
            for call in original_calls:
                if hasattr(call, "apply"):
                    call.apply(temp_ctx)
                # print(call.get_required_resources_recursively())
                required_resources = call.get_required_resources_recursively()
                print(f"Call {call} required resources: {required_resources}")
                # 这里可以检查调用是否使用了这些资源
                for res in required_resources:
                    if res["type"] == res_type and res["name"] == res_name:
                        print(f"Call {call} uses resource {res_type} {res_name}")
                        # 这里可以添加逻辑来处理这些调用，比如打印或修改它们
                        # 例如，打印调用的类型和名称
                        print(
                            f"Call type: {type(call).__name__}, Call name: {call.name if hasattr(call, 'name') else 'N/A'}"
                        )
                        # 然后可以在这里进行替换操作
                        # 例如，假设我们要替换为一个新的资源，可以这样做：
                        new_resource = temp_ctx.tracker.random_choose(res_type, exclude=res_name)
                        print(new_resource)
                        if new_resource:
                            print(f"Replacing {res_type} {res_name} with {new_resource}")
                            if hasattr(call, "set_resource"):
                                # 假设call有一个set_resource方法来设置资源
                                call.set_resource_recursively(res_type, res_name, new_resource)
                            else:
                                print(f"Call {call} does not support resource replacement.")
                        else:
                            # print(f"No suitable replacement found for {res_type} {res_name}.")
                            raise ValueError(f"No suitable replacement found for {res_type} {res_name}.")
                            # 假设call有一个set_resource方法来设置资源
                            # if hasattr(call, 'set_resource'):
                            #     call.set_resource(res_type, new_resource)
                            # else:
                            #     print(f"Call {call} does not support resource replacement.")
                # if hasattr(call, 'required_resources') and (res_type, res_name) in call.required_resources:
                #     print(f"Call {call} uses resource {res_type} {res_name}")
                #     # 这里可以添加逻辑来处理这些调用，比如打印或修改它们
                #     # 例如，打印调用的类型和名称
                #     print(f"Call type: {type(call).__name__}, Call name: {call.name if hasattr(call, 'name') else 'N/A'}")
                #     # 然后可以在这里进行替换操作
                #     # 例如，假设我们要替换为一个新的资源，可以这样做：
                #     new_resource = ctx.tracker.random_choose(res_type, exclude=res_name)
                #     if new_resource:
                #         print(f"Replacing {res_type} {res_name} with {new_resource}")
                #         # 假设call有一个set_resource方法来设置资源
                #         if hasattr(call, 'set_resource'):
                #             call.set_resource(res_type, new_resource)
                #         else:
                #             print(f"Call {call} does not support resource replacement.")
        new_ctx = CodeGenContext()
        for call in original_calls:
            if hasattr(call, "apply"):
                call.apply(new_ctx)
            pass
    return original_calls
    # this is a sketch
    # 如果需要打印所有分配的资源，可以取消注释以下代码
    # for res_type, res_list in allocated_resources.items():
    #     print(f"Resource type: {res_type}")
    #     for res in res_list:
    #         print(f"  Resource: {res}")

    return None  # 这里返回None，表示不需要生成代码


def write_and_compile_code(rendered_code: str, filename: str = "test.cpp", executable_name: str = "test"):
    """Write the rendered code to a file and compile it."""
    with open(filename, "w") as f:
        f.write(rendered_code)
    print(f"Generated {filename}")
    os.system(f"g++ -o {executable_name} {filename} -lcjson -libverbs")


if __name__ == "__main__":
    rendered = generate_replay_code_client(1024)
    write_and_compile_code(rendered, "test.cpp", "test")

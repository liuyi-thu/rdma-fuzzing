from codegen_context import CodeGenContext
from verbs import *
import os
from typing import List, Dict
import json


def parse_trace(json_path: str, ctx) -> List[VerbCall]:
    """Read trace_output.json and convert to VerbCall list."""
    calls: List[VerbCall] = []
    with open(json_path, "r") as fp:
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


def generate_replay_code_fixed(buf_size, server_name="192.168.56.11"):
    ctx = CodeGenContext()
    calls = [
        # Connect or wait depending on server_name
        SockConnect(server_name=server_name, port=19875),
        # resources_create start
        GetDeviceList(),
        OpenDevice(),
        FreeDeviceList(),
        QueryDeviceAttr(),
        QueryPortAttr(),
        AllocPD(pd_addr="PD", ctx=ctx),
        CreateCQ(cq_addr="CQ", ctx=ctx),
        RegMR(pd_addr="PD", buf="buf", length=buf_size, mr_addr="MR",
              flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE", ctx=ctx),
        CreateQP(pd_addr="PD", qp_addr="QP", qp_type="IBV_QPT_RC", cap_params={
            "max_send_wr": 1,
            "max_recv_wr": 1,
            "max_send_sge": 1,
            "max_recv_sge": 1}, ctx=ctx),
        # resources_create end
        # connect_qp start
        QueryGID(),  # Query GID for the local port
        SockSyncData(),  # Synchronize connection data over socket
        # modify QP to INIT state
        ModifyQP(qp_addr="QP", state="IBV_QPS_INIT"),
        PostRecv(qp_addr="QP", wr_id="0"),  # Post a receive request
        # modify QP to RTR state
        # 这是一个问题，remote_qpn和dlid应该从远端获取，暂时写死为1和0
        ModifyQPToRTR(qp_addr="QP", remote_qpn=1, dlid=0, dgid="0"),
        # modify QP to RTS state
        ModifyQPToRTS(qp_addr="QP"),
        SockSyncDummy(),  # Dummy sync, no actual data transfer
        # connect_qp end
        # post_send start
        PostSend(qp_addr="QP", wr_id="1", opcode="IBV_WR_SEND"),
        PollCQ(cq_addr="CQ"),
        # post_send end
        SockSyncDummy(char="R"),  # Dummy sync, no actual data transfer
        DestroyQP(qp_addr="QP"),  # Destroy the QP
        DestroyMR(mr_addr="MR"),  # Destroy the MR
        DestroyCQ(cq_addr="CQ"),  # Destroy the CQ
        DestroyPD(pd_addr="PD"),  # Destroy the PD
        CloseDevice(),  # Close the device context
        SocketClose(sock="sock")  # Close the socket connection
    ]

    header = f"""#include <stdio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>
#include <inttypes.h>
#include <endian.h>
#include <byteswap.h>
#include <getopt.h>
#include <sys/time.h>
#include <arpa/inet.h>
#include <infiniband/verbs.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>\n

#define MAX_POLL_CQ_TIMEOUT 2000
#define MSG_S "SEND operation from server"
#define MSG_C "SEND operation from client"
#define RDMAMSGR "RDMA read operation "
#define RDMAMSGW "RDMA write operation"
#define MSG_SIZE 64
#if __BYTE_ORDER == __LITTLE_ENDIAN
static inline uint64_t htonll(uint64_t x)
{{
    return bswap_64(x);
}}
static inline uint64_t ntohll(uint64_t x)
{{
    return bswap_64(x);
}}
#elif __BYTE_ORDER == __BIG_ENDIAN
static inline uint64_t htonll(uint64_t x)
{{
    return x;
}}
static inline uint64_t ntohll(uint64_t x)
{{
    return x;
}}
#else
#error __BYTE_ORDER is neither __LITTLE_ENDIAN nor __BIG_ENDIAN
#endif

struct ibv_context *ctx;
struct ibv_pd *pd[10];
struct ibv_cq *cq[10];
struct ibv_qp *qp[10];
struct ibv_mr *mr[10];
struct ibv_device **dev_list;
struct ibv_device_attr {ctx.dev_attr};
struct ibv_port_attr {ctx.port_attr};
struct cm_con_data_t local_con_data;
struct cm_con_data_t remote_con_data;
struct cm_con_data_t tmp_con_data;
struct cm_con_data_t remote_props;
union ibv_gid my_gid;

int sock;
char temp_char;
char buf[{buf_size}];\n

struct cm_con_data_t
{{
    uint64_t addr;        /* Buffer address */
    uint32_t rkey;        /* Remote key */
    uint32_t qp_num;      /* QP number */
    uint16_t lid;         /* LID of the IB port */
    uint8_t gid[16];      /* gid */
}} __attribute__((packed));

static int sock_connect(const char *servername, int port)
{{
    struct addrinfo *resolved_addr = NULL;
    struct addrinfo *iterator;
    char service[6];
    int sockfd = -1;
    int listenfd = 0;
    int tmp;
    struct addrinfo hints =
    {{
        .ai_flags    = AI_PASSIVE,
        .ai_family   = AF_INET,
        .ai_socktype = SOCK_STREAM
    }};

    if(sprintf(service, "%d", port) < 0)
    {{
        goto sock_connect_exit;
    }}

    /* Resolve DNS address, use sockfd as temp storage */
    sockfd = getaddrinfo(servername, service, &hints, &resolved_addr);
    if(sockfd < 0)
    {{
        fprintf(stderr, "%s for %s:%d\\n", gai_strerror(sockfd), servername, port);
        goto sock_connect_exit;
    }}

    /* Search through results and find the one we want */
    for(iterator = resolved_addr; iterator ; iterator = iterator->ai_next)
    {{
        sockfd = socket(iterator->ai_family, iterator->ai_socktype, iterator->ai_protocol);
        if(sockfd >= 0)
        {{
            if(servername)
            {{
                /* Client mode. Initiate connection to remote */
                if((tmp=connect(sockfd, iterator->ai_addr, iterator->ai_addrlen)))
                {{
                    fprintf(stdout, "failed connect \\n");
                    close(sockfd);
                    sockfd = -1;
                }}
            }}
            else
            {{
                /* Server mode. Set up listening socket an accept a connection */
                listenfd = sockfd;
                sockfd = -1;
                if(bind(listenfd, iterator->ai_addr, iterator->ai_addrlen))
                {{
                    goto sock_connect_exit;
                }}
                listen(listenfd, 1);
                sockfd = accept(listenfd, NULL, 0);
            }}
        }}
    }}

sock_connect_exit:
    if(listenfd)
    {{
        close(listenfd);
    }}

    if(resolved_addr)
    {{
        freeaddrinfo(resolved_addr);
    }}

    if(sockfd < 0)
    {{
        if(servername)
        {{
            fprintf(stderr, "Couldn't connect to %s:%d\\n", servername, port);
        }}
        else
        {{
            perror("server accept");
            fprintf(stderr, "accept() failed\\n");
        }}
    }}

    return sockfd;
}}
int sock_sync_data(int sock, int xfer_size, char *local_data, char *remote_data)
{{
    int rc;
    int read_bytes = 0;
    int total_read_bytes = 0;
    rc = write(sock, local_data, xfer_size);

    if(rc < xfer_size)
    {{
        fprintf(stderr, "Failed writing data during sock_sync_data\\n");
    }}
    else
    {{
        rc = 0;
    }}

    while(!rc && total_read_bytes < xfer_size)
    {{
        read_bytes = read(sock, remote_data, xfer_size);
        if(read_bytes > 0)
        {{
            total_read_bytes += read_bytes;
        }}
        else
        {{
            rc = read_bytes;
        }}
    }}
    return rc;
}}

int main() {{
"""
    body = "".join(call.generate_c(ctx) for call in calls)
    footer = """\n return 0;\n}\n"""
    code = header + body + footer
    return code

# # for testing purposes, you can run this script directly
# if __name__  == "__main__":
#     import sys
#     if len(sys.argv) != 2:
#         print("Usage: python verbs_replay.py <trace_output.json>")
#         sys.exit(1)

#     trace_file = sys.argv[1]
#     code = generate_replay_code(trace_file)
#     print(code)


if __name__ == "__main__":
    # Example usage generating server side code by passing server_name=None
    code = generate_replay_code_fixed(buf_size=4096, server_name="192.168.56.11")
    print(code)
    with open("verbs_replay_fixed.c", "w") as f:
        f.write(code)
    os.system('gcc -o verbs_replay_fixed verbs_replay_fixed.c  -libverbs -g')

    # ctx = CodeGenContext()
    # calls = parse_trace("trace_output.json", ctx)
    # code = "".join(call.generate_c(ctx) for call in calls)
    # print(code)

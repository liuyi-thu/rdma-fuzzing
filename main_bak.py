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


def generate_replay_code_server(buf_size, server_name=None):
    ctx = CodeGenContext()
    calls = [
        # Connect or wait depending on server_name
        SockConnect(server_name=server_name, port=19875),
        # resources_create start
        GetDeviceList(),
        OpenDevice(),
        FreeDeviceList(),
        QueryDeviceAttr(),
        QueryPortAttr()
    ]
    for i in range(ctx.max_QPs):
        calls += [
            AllocPD(pd_addr=f"PD{i}", ctx=ctx),
            CreateCQ(cq_addr=f"CQ{i}", ctx=ctx),
            RegMR(pd_addr=f"PD{i}", buf=f"bufs[{i}]", length=buf_size, mr_addr=f"MR{i}",
                  flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE", ctx=ctx),
            CreateQP(pd_addr=f"PD{i}", qp_addr=f"QP{i}", cq_addr=f"CQ{i}", qp_type="IBV_QPT_RC", cap_params={
                "max_send_wr": 1,
                "max_recv_wr": 1,
                "max_send_sge": 1,
                "max_recv_sge": 1}, ctx=ctx),
            QueryGID(),  # Query GID for the local port
            ExportQPInfo(qp_addr=f"QP{i}", mr_addr=f"MR{i}"),  # Export QP info
            SockSyncData(),  # Synchronize connection data over socket
            ImportQPInfo(i),  # Import QP info from remote
        ]
    for i in range(ctx.max_QPs):
        calls += [
            ModifyQP(qp_addr=f"QP{i}", state="IBV_QPS_INIT"),
            ModifyQPToRTR(qp_addr=f"QP{i}", qpn = i),
            ModifyQPToRTS(qp_addr=f"QP{i}"),
            SockSyncDummy(),  # Dummy sync, no actual data transfer
            PostSend(qp_addr=f"QP{i}", mr_addr = f"MR{i}", wr_id="1", opcode="IBV_WR_SEND"),
            PollCQ(cq_addr=f"CQ{i}"),
        ]
    for i in range(ctx.max_QPs):
        calls += [
            DestroyQP(qp_addr=f"QP{i}"),  # Destroy the QP
            DestroyMR(mr_addr=f"MR{i}"),  # Destroy the MR
            DestroyCQ(cq_addr=f"CQ{i}"),  # Destroy the CQ
            DestroyPD(pd_addr=f"PD{i}"),  # Destroy the PD
        ]
    calls += [
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

struct cm_con_data_t
{{
    uint64_t addr;        /* Buffer address */
    uint32_t rkey;        /* Remote key */
    uint32_t qp_num;      /* QP number */
    uint16_t lid;         /* LID of the IB port */
    uint8_t gid[16];      /* gid */
}} __attribute__((packed));

struct ibv_context *ctx;
struct ibv_pd *pd[{ctx.max_QPs}];
struct ibv_cq *cq[{ctx.max_QPs}];
struct ibv_qp *qp[{ctx.max_QPs}];
struct ibv_mr *mr[{ctx.max_QPs}];
struct ibv_device **dev_list;
struct ibv_device_attr {ctx.dev_attr};
struct ibv_port_attr {ctx.port_attr};
struct cm_con_data_t local_con_data;
struct cm_con_data_t remote_con_data;
struct cm_con_data_t remote_con_datas[{ctx.max_QPs}];
struct cm_con_data_t tmp_con_data;
struct cm_con_data_t remote_props;
union ibv_gid my_gid;

int sock;
char temp_char;
char buf[{buf_size}];
char bufs[{ctx.max_QPs}][{buf_size}];

struct ibv_wc wc;
unsigned long start_time_msec;
unsigned long cur_time_msec;
struct timeval cur_time;
int poll_result;
int rc = 0;
    
\n

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

def generate_replay_code_client(buf_size, server_name=None):
    ctx = CodeGenContext()
    ctx = CodeGenContext()
    calls = [
        # Connect or wait depending on server_name
        SockConnect(server_name=server_name, port=19875),
        # resources_create start
        GetDeviceList(),
        OpenDevice(),
        FreeDeviceList(),
        QueryDeviceAttr(),
        QueryPortAttr()
    ]
    for i in range(ctx.max_QPs):
        calls += [
            AllocPD(pd_addr=f"PD{i}", ctx=ctx),
            CreateCQ(cq_addr=f"CQ{i}", ctx=ctx),
            RegMR(pd_addr=f"PD{i}", buf=f"bufs[{i}]", length=buf_size, mr_addr=f"MR{i}",
                  flags="IBV_ACCESS_LOCAL_WRITE | IBV_ACCESS_REMOTE_READ | IBV_ACCESS_REMOTE_WRITE", ctx=ctx),
            CreateQP(pd_addr=f"PD{i}", qp_addr=f"QP{i}", cq_addr=f"CQ{i}", qp_type="IBV_QPT_RC", cap_params={
                "max_send_wr": 1,
                "max_recv_wr": 1,
                "max_send_sge": 1,
                "max_recv_sge": 1}, ctx=ctx),
            QueryGID(),  # Query GID for the local port
            ExportQPInfo(qp_addr=f"QP{i}", mr_addr=f"MR{i}"),  # Export QP info
            SockSyncData(),  # Synchronize connection data over socket
            ImportQPInfo(i),  # Import QP info from remote
        ]
    for i in range(ctx.max_QPs):
        calls += [
            ModifyQP(qp_addr=f"QP{i}", state="IBV_QPS_INIT"),
            PostRecv(qp_addr=f"QP{i}", mr_addr = f"MR{i}", wr_id="1"),
            ModifyQPToRTR(qp_addr=f"QP{i}", qpn = i),
            ModifyQPToRTS(qp_addr=f"QP{i}"),
            SockSyncDummy(),  # Dummy sync, no actual data transfer
            PollCQ(cq_addr=f"CQ{i}"),
        ]
    for i in range(ctx.max_QPs):
        calls += [
            DestroyQP(qp_addr=f"QP{i}"),  # Destroy the QP
            DestroyMR(mr_addr=f"MR{i}"),  # Destroy the MR
            DestroyCQ(cq_addr=f"CQ{i}"),  # Destroy the CQ
            DestroyPD(pd_addr=f"PD{i}"),  # Destroy the PD
        ]
    calls += [
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

struct cm_con_data_t
{{
    uint64_t addr;        /* Buffer address */
    uint32_t rkey;        /* Remote key */
    uint32_t qp_num;      /* QP number */
    uint16_t lid;         /* LID of the IB port */
    uint8_t gid[16];      /* gid */
}} __attribute__((packed));


struct ibv_context *ctx;
struct ibv_pd *pd[{ctx.max_QPs}];
struct ibv_cq *cq[{ctx.max_QPs}];
struct ibv_qp *qp[{ctx.max_QPs}];
struct ibv_mr *mr[{ctx.max_QPs}];
struct ibv_device **dev_list;
struct ibv_device_attr {ctx.dev_attr};
struct ibv_port_attr {ctx.port_attr};
struct cm_con_data_t local_con_data;
struct cm_con_data_t remote_con_data;
struct cm_con_data_t remote_con_datas[{ctx.max_QPs}];
struct cm_con_data_t tmp_con_data;
struct cm_con_data_t remote_props;
union ibv_gid my_gid;

int sock;
char temp_char;
char buf[{buf_size}];
char bufs[{ctx.max_QPs}][{buf_size}];

struct ibv_wc wc;
unsigned long start_time_msec;
unsigned long cur_time_msec;
struct timeval cur_time;
int poll_result;
int rc = 0;
    
\n

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

if __name__ == "__main__":
    # Example usage generating server side code by passing server_name=None
    code = generate_replay_code_client(buf_size=4096, server_name="192.168.56.11")
    # code = generate_replay_code_fixed(buf_size=4096, server_name=None)
    # print(code)
    with open("verbs_replay.c", "w") as f:
        f.write(code)
    os.system('gcc -o verbs_replay_fixed_client verbs_replay.c  -libverbs -g')

    code = generate_replay_code_server(buf_size=4096, server_name=None)
    # code = generate_replay_code_fixed(buf_size=4096, server_name=None)
    # print(code)
    with open("verbs_replay.c", "w") as f:
        f.write(code)
    os.system('gcc -o verbs_replay_fixed_server verbs_replay.c  -libverbs -g')

    # ctx = CodeGenContext()
    # calls = parse_trace("trace_output.json", ctx)
    # code = "".join(call.generate_c(ctx) for call in calls)
    # print(code)

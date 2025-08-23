#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "runtime_resolver.h"

// // 可选：把 union ibv_gid 定义一下（如果你没包含 <infiniband/verbs.h>）
// typedef union {
//     uint8_t raw[16];
// } ibv_gid_like;

// // 声明 parse_gid_str，如果你把实现放在 runtime_resolver.c；或者将声明放入其头文件
// int parse_gid_str(const char *s, ibv_gid_like *out);

// static void print_gid_hex(const ibv_gid_like *g) {
//     for (int i = 0; i < 16; ++i) {
//         printf("%02x%s", g->raw[i], (i == 15) ? "" : ":");
//     }
//     printf("\n");
// }

static void print_gid_hex(const union ibv_gid *g) {
    for (int i = 0; i < 16; ++i) {
        printf("%02x%s", g->raw[i], (i == 15) ? "" : ":");
    }
    printf("\n");
}

int main(void) {
    // 1) 从环境变量加载 bundle
    //    export RDMA_FUZZ_RUNTIME=$PWD/runtime.json
    rr_load_from_env_or_die("RDMA_FUZZ_RUNTIME");

    printf("=== PATH-STYLE LOOKUP ===\n");
    // 2) 按“路径 + 下标”取值
    uint32_t qpn0 = rr_u32("remote.QP[0].qpn");
    uint32_t psn0 = rr_u32("remote.QP[0].psn");
    uint32_t port0 = rr_u32("remote.QP[0].port");
    const char *gid_str0 = rr_str("remote.QP[0].gid");
    printf("remote.QP[0].qpn=%u, psn=%u, port=%u, gid=%s\n", qpn0, psn0, port0, gid_str0);

    uint64_t raddr = rr_u64("remote.MR[0].addr");
    uint32_t rkey  = rr_u32("remote.MR[0].rkey");
    printf("remote.MR[0].addr=%llu, rkey=%u\n", (unsigned long long)raddr, rkey);

    uint64_t laddr = rr_u64("local.MR[0].addr");
    uint32_t lkey  = rr_u32("local.MR[0].lkey");
    printf("local.MR[0].addr=%llu, lkey=%u\n", (unsigned long long)laddr, lkey);

    printf("\n=== ID-STYLE LOOKUP ===\n");
    // 3) 按“数组键 + id + 字段”取值
    uint32_t qpn_peer0 = rr_u32_by_id("remote.QP", "peer0", "qpn");
    uint32_t psn_peer0 = rr_u32_by_id("remote.QP", "peer0", "psn");
    const char *gid_peer0 = rr_str_by_id("remote.QP", "peer0", "gid");
    printf("remote.QP[id=peer0].qpn=%u, psn=%u, gid=%s\n", qpn_peer0, psn_peer0, gid_peer0);

    uint64_t raddr_rbuf0 = rr_u64_by_id("remote.MR", "rbuf0", "addr");
    uint32_t rkey_rbuf0  = rr_u32_by_id("remote.MR", "rbuf0", "rkey");
    printf("remote.MR[id=rbuf0].addr=%llu, rkey=%u\n", (unsigned long long)raddr_rbuf0, rkey_rbuf0);

    // 4) 将字符串 GID 解析为 16B 的 union ibv_gid
    printf("\n=== parse_gid_str DEMO ===\n");
    union ibv_gid g = {0};
    if (parse_gid_str(gid_peer0, &g) == 0) {
        printf("gid (hex): ");
        print_gid_hex(&g);
    } else {
        printf("parse_gid_str failed for: %s\n", gid_peer0);
    }

    // 5) 存在性检查（可选）
    printf("\n=== EXISTS CHECK ===\n");
    printf("has remote.QP[0].qpn? %d\n", rr_has("remote.QP[0].qpn"));
    printf("has remote.QP[1].qpn? %d\n", rr_has("remote.QP[1].qpn")); // 预计为 0

    printf("\nOK.\n");
    return 0;
}


// pair_runtime.h
// Helpers for RDMA fuzz-generated clients to coordinate with server via coordinator views.
// Provides: init, JSON update writers (CLAIMED/READY), wait for pair state,
// and by-id resolution of remote QP/MR attributes.
//
// Build: compile this with your client along with runtime_resolver.c and cJSON.c
// g++ ... pair_runtime.cpp runtime_resolver.c cJSON.c -libverbs -pthread ...

#pragma once
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// ---------------- Public PODs to describe local resources ----------------
typedef struct {
    const char* id;     // e.g., "cli0"
    uint32_t    qpn;    // local QP number
    uint32_t    psn;    // optional (0 if unknown)
    uint8_t     port;   // HCA port (default 1)
    uint16_t    lid;    // optional (0 if unknown)
    const char* gid;    // string "xx:..:xx" (16 bytes hex, colon-separated), or NULL
} PR_QP;

typedef struct {
    const char* id;     // e.g., "sbuf_cli0"
    uint64_t    addr;
    uint32_t    length;
    uint32_t    lkey;
} PR_MR;

typedef struct {
    const char* id;     // e.g., "pair-cli0-srv0"
    const char* cli_id; // local QP id, e.g., "cli0"
    const char* srv_id; // desired remote QP id, e.g., "srv0"
} PR_Pair;

// ---------------- Initialization ----------------
// Initialize inotify (if available) and load RDMA_FUZZ_RUNTIME environment view once.
void pr_init(const char* bundle_env);

// ---------------- Client update writers ----------------
// Write client_update.json with pairs state = CLAIMED (or READY). Atomic write.
void pr_write_client_update_claimed(const char* path,
                                    const PR_QP* qps, int n_qp,
                                    const PR_MR* mrs, int n_mr,
                                    const PR_Pair* pairs, int n_pair);

void pr_write_client_update_ready(const char* path,
                                  const PR_QP* qps, int n_qp,
                                  const PR_MR* mrs, int n_mr,
                                  const PR_Pair* pairs, int n_pair);

// ---------------- Pair state waiting (event-driven if possible) ----------------
bool pr_wait_pair_state(const char* bundle_env, const char* pair_id,
                        const char* expect_state, int timeout_ms);

// ---------------- Resolver helpers (by-id) ----------------
bool pr_resolve_remote_qp(const char* srv_id,
                          uint32_t* qpn, uint32_t* psn,
                          uint16_t* lid, uint8_t gid[16], uint8_t* port);

bool pr_resolve_remote_mr(const char* mr_id,
                          uint64_t* addr, uint32_t* rkey, uint32_t* length);

// ---------------- Small utilities ----------------
// Parse colon-separated 16-byte GID string into out[16]; returns true on success.
bool pr_parse_gid(const char* gid_str, uint8_t out16[16]);

#ifdef __cplusplus
}
#endif

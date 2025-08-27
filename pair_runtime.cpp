
// pair_runtime.cpp
#include "pair_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <inttypes.h>
#include <string>
#include <vector>
#include <mutex>
#include <chrono>
#include <thread>

#ifdef __linux__
#include <sys/inotify.h>
#include <unistd.h>
#include <libgen.h>
#endif

extern "C"
{
#include <cjson/cJSON.h>
#include "runtime_resolver.h"
}

using std::string;
using std::vector;

static uint64_t now_ms()
{
    using namespace std::chrono;
    return (uint64_t)std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

// -------- runtime_resolver global lock (avoid races between reload and rr_* reads) --------
static std::mutex g_rr_mtx;
struct RRLock
{
    RRLock() { g_rr_mtx.lock(); }
    ~RRLock() { g_rr_mtx.unlock(); }
};
static inline void rr_reload_locked(const char *env)
{
    RRLock lk;
    rr_load_from_env_or_die(env);
}

// ---------------- inotify reloader (Linux only; otherwise falls back to polling reload) ----------------
struct InotifyReloader
{
#ifdef __linux__
    int fd = -1;
    int wd = -1;
    string watch_dir;
    string watch_base;
    bool init_from_env(const char *env_key)
    {
        const char *p = getenv(env_key);
        if (!p)
            return false;
        char buf[1024];
        snprintf(buf, sizeof(buf), "%s", p);
        char *dirc = strdup(buf);
        char *basec = strdup(buf);
        watch_dir = dirname(dirc);
        watch_base = basename(basec);
        free(dirc);
        free(basec);
        fd = inotify_init1(IN_NONBLOCK);
        if (fd < 0)
            return false;
        wd = inotify_add_watch(fd, watch_dir.c_str(), IN_CLOSE_WRITE | IN_MOVED_TO | IN_ATTRIB);
        if (wd < 0)
        {
            close(fd);
            fd = -1;
            return false;
        }
        return true;
    }
    bool pump_and_reload(const char *env_key)
    {
        if (fd < 0)
            return false;
        char buf[4096];
        ssize_t n = read(fd, buf, sizeof(buf));
        if (n <= 0)
            return false;
        size_t i = 0;
        bool reload = false;
        while (i < (size_t)n)
        {
            auto *ev = (struct inotify_event *)(buf + i);
            if (ev->len > 0 && (ev->mask & (IN_CLOSE_WRITE | IN_MOVED_TO | IN_ATTRIB)))
            {
                if (watch_base == ev->name)
                    reload = true;
            }
            i += sizeof(struct inotify_event) + ev->len;
        }
        if (reload)
        {
            rr_reload_locked(env_key);
            return true;
        }
        return false;
    }
#else
    bool init_from_env(const char *) { return false; }
    bool pump_and_reload(const char *) { return false; }
#endif
};

static InotifyReloader g_rld;

void pr_init(const char *bundle_env)
{
    rr_reload_locked(bundle_env);
    g_rld.init_from_env(bundle_env);
}

// ---------------- JSON writers ----------------
static void atomic_write_json(const char *path, cJSON *root)
{
    char tmp[512];
    snprintf(tmp, sizeof(tmp), "%s.tmp", path);
    FILE *f = fopen(tmp, "w");
    if (!f)
    {
        perror("open tmp");
        return;
    }
    char *txt = cJSON_PrintBuffered(root, 1 << 20, 1);
    fputs(txt, f);
    fclose(f);
    free(txt);
    if (rename(tmp, path) != 0)
        perror("rename");
}

static void write_update_with_state(const char *path,
                                    const PR_QP *qps, int n_qp,
                                    const PR_MR *mrs, int n_mr,
                                    const PR_Pair *pairs, int n_pair,
                                    const char *state)
{
    cJSON *root = cJSON_CreateObject();
    cJSON *local = cJSON_AddObjectToObject(root, "local");
    cJSON *arr_qp = cJSON_AddArrayToObject(local, "QP");
    cJSON *arr_mr = cJSON_AddArrayToObject(local, "MR");
    cJSON *arr_pairs = cJSON_AddArrayToObject(local, "pairs");
    // QPs
    for (int i = 0; i < n_qp; ++i)
    {
        const PR_QP &q = qps[i];
        cJSON *o = cJSON_CreateObject();
        if (q.id)
            cJSON_AddStringToObject(o, "id", q.id);
        cJSON_AddNumberToObject(o, "qpn", q.qpn);
        cJSON_AddNumberToObject(o, "psn", q.psn);
        cJSON_AddNumberToObject(o, "port", (int)q.port);
        cJSON_AddNumberToObject(o, "lid", q.lid);
        cJSON_AddStringToObject(o, "gid", q.gid ? q.gid : "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00");
        cJSON_AddItemToArray(arr_qp, o);
    }
    // MRs
    for (int i = 0; i < n_mr; ++i)
    {
        const PR_MR &m = mrs[i];
        cJSON *o = cJSON_CreateObject();
        if (m.id)
            cJSON_AddStringToObject(o, "id", m.id);
        cJSON_AddNumberToObject(o, "addr", (double)m.addr);
        cJSON_AddNumberToObject(o, "length", m.length);
        cJSON_AddNumberToObject(o, "lkey", m.lkey);
        cJSON_AddItemToArray(arr_mr, o);
    }
    // Pairs
    uint64_t ts = now_ms();
    for (int i = 0; i < n_pair; ++i)
    {
        const PR_Pair &p = pairs[i];
        cJSON *o = cJSON_CreateObject();
        if (p.id)
            cJSON_AddStringToObject(o, "id", p.id);
        if (p.cli_id)
            cJSON_AddStringToObject(o, "cli_id", p.cli_id);
        if (p.srv_id)
            cJSON_AddStringToObject(o, "srv_id", p.srv_id);
        cJSON_AddStringToObject(o, "state", state);
        cJSON_AddNumberToObject(o, "ts", (double)ts);
        cJSON_AddItemToArray(arr_pairs, o);
    }
    atomic_write_json(path, root);
    cJSON_Delete(root);
}

void pr_write_client_update_claimed(const char *path,
                                    const PR_QP *qps, int n_qp,
                                    const PR_MR *mrs, int n_mr,
                                    const PR_Pair *pairs, int n_pair)
{
    write_update_with_state(path, qps, n_qp, mrs, n_mr, pairs, n_pair, "CLAIMED");
}

void pr_write_client_update_ready(const char *path,
                                  const PR_QP *qps, int n_qp,
                                  const PR_MR *mrs, int n_mr,
                                  const PR_Pair *pairs, int n_pair)
{
    write_update_with_state(path, qps, n_qp, mrs, n_mr, pairs, n_pair, "READY");
}

// ---------------- Wait for pair state ----------------
bool pr_wait_pair_state(const char *bundle_env, const char *pair_id,
                        const char *expect_state, int timeout_ms)
{
    uint64_t deadline = now_ms() + (timeout_ms > 0 ? (uint64_t)timeout_ms : 0ULL);
    while (timeout_ms <= 0 || (int64_t)(deadline - now_ms()) > 0)
    {
        // pump inotify if available, else reload every loop
        if (!g_rld.pump_and_reload(bundle_env))
        {
            // fallback to polling reload
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
            rr_reload_locked(bundle_env);
        }
        // check state
        {
            RRLock lk;
            for (int i = 0;; ++i)
            {
                char key[256];
                snprintf(key, sizeof(key), "pairs[%d].id", i);
                if (!rr_has(key))
                    break;
                const char *id = rr_str(key);
                if (id && strcmp(id, pair_id) == 0)
                {
                    snprintf(key, sizeof(key), "pairs[%d].state", i);
                    const char *st = rr_str(key);
                    if (st && strcmp(st, expect_state) == 0)
                        return true;
                }
            }
        }
    }
    return false;
}

// ---------------- Resolve helpers ----------------
bool pr_parse_gid(const char *gid_str, uint8_t out16[16])
{
    if (!gid_str || !out16)
        return false;
    unsigned int bb[16] = {0};
    int n = sscanf(gid_str,
                   "%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x:%2x",
                   &bb[0], &bb[1], &bb[2], &bb[3], &bb[4], &bb[5], &bb[6], &bb[7],
                   &bb[8], &bb[9], &bb[10], &bb[11], &bb[12], &bb[13], &bb[14], &bb[15]);
    if (n != 16)
        return false;
    for (int i = 0; i < 16; ++i)
        out16[i] = (uint8_t)bb[i];
    return true;
}

bool pr_resolve_remote_qp(const char *srv_id,
                          uint32_t *qpn, uint32_t *psn,
                          uint16_t *lid, uint8_t gid[16], uint8_t *port)
{
    RRLock lk;
    // by-id preferred
    if (rr_has("remote.ids.QP[0]"))
    {
        if (qpn)
            *qpn = rr_u32_by_id("remote.QP", srv_id, "qpn");
        if (psn)
            *psn = rr_try_u32_by_id("remote.QP", srv_id, "psn", 0);
        if (port)
            *port = (uint8_t)rr_try_u32_by_id("remote.QP", srv_id, "port", 1);
        if (lid)
            *lid = (uint16_t)rr_try_u32_by_id("remote.QP", srv_id, "lid", 0);
        const char *g = rr_try_str_by_id("remote.QP", srv_id, "gid", "00:00:...:00");
        if (gid)
            pr_parse_gid(g, gid);
        return true;
    }
    // fallback to first remote
    if (qpn)
        *qpn = rr_u32("remote.QP[0].qpn");
    if (psn)
        *psn = rr_try_u32("remote.QP[0].psn", 0);
    if (port)
        *port = (uint8_t)rr_try_u32("remote.QP[0].port", 1);
    if (lid)
        *lid = (uint16_t)rr_try_u32("remote.QP[0].lid", 0);
    const char *g = rr_try_str("remote.QP[0].gid", "00:00:...:00");
    if (gid)
        pr_parse_gid(g, gid);
    return true;
}

bool pr_resolve_remote_mr(const char *mr_id,
                          uint64_t *addr, uint32_t *rkey, uint32_t *length)
{
    RRLock lk;
    if (rr_has("remote.MR[0].id") || rr_has("remote.ids.MR[0]"))
    {
        if (rr_has("remote.ids.MR[0]"))
        {
            if (addr)
                *addr = rr_u64_by_id("remote.MR", mr_id, "addr");
            if (rkey)
                *rkey = rr_u32_by_id("remote.MR", mr_id, "rkey");
            if (length)
                *length = rr_try_u32_by_id("remote.MR", mr_id, "length", 0);
            return true;
        }
        // fallback first remote MR
        if (addr)
            *addr = rr_u64("remote.MR[0].addr");
        if (rkey)
            *rkey = rr_u32("remote.MR[0].rkey");
        if (length)
            *length = rr_try_u32("remote.MR[0].length", 0);
        return true;
    }
    return false;
}

// 把16字节的GID数组转为字符串 "xx:xx:...:xx"
bool pr_gid_to_str(const uint8_t in16[16], char *out_str, size_t out_len)
{
    if (!in16 || !out_str || out_len < 48)
    {
        // 16*2(hex)+15(colons)+1('\0') = 48
        return false;
    }
    int n = snprintf(out_str, out_len,
                     "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x:"
                     "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x",
                     in16[0], in16[1], in16[2], in16[3],
                     in16[4], in16[5], in16[6], in16[7],
                     in16[8], in16[9], in16[10], in16[11],
                     in16[12], in16[13], in16[14], in16[15]);
    return (n > 0 && n < (int)out_len);
}
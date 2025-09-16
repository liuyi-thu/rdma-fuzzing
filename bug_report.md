OK，我写了一封给开发者的邮件，你看一下有没有要修改or润色的：
Subject: [BUG] libibverbs: ibv_create_qp crashes when recv_cq=NULL (expected EINVAL)

Hi RDMA maintainers,

I would like to report a robustness issue in libibverbs (rdma-core).

**Environment:**
- Distro: Ubuntu 22.04 (kernel 6.8.0-65-generic)
- rdma-core version: 39.0-1
- libibverbs version: 39.0-1 (package: libibverbs1:amd64)
- Provider: rxe
- Reproduced with both gdb and ASan

**Problem description:**
When calling `ibv_create_qp()` with `attr.recv_cq = NULL` (while qp_type=IBV_QPT_RC),
the process crashes inside `ibv_icmd_create_qp()` due to an unconditional
dereference of `attr_ex->recv_cq->handle`.  
Instead of returning `-1` with `errno = EINVAL`, libibverbs causes a
segmentation fault.

**Minimal reproducer:**
```c
#include <infiniband/verbs.h>
#include <stdio.h>
#include <stdlib.h>

int main() {
    int num;
    struct ibv_device **list = ibv_get_device_list(&num);
    struct ibv_context *ctx = ibv_open_device(list[0]);
    struct ibv_pd *pd = ibv_alloc_pd(ctx);

    struct ibv_cq *send_cq = ibv_create_cq(ctx, 16, NULL, NULL, 0);

    struct ibv_qp_init_attr attr = {0};
    attr.qp_type = IBV_QPT_RC;
    attr.cap.max_send_wr = 1;
    attr.cap.max_recv_wr = 1;
    attr.cap.max_send_sge = 1;
    attr.cap.max_recv_sge = 1;
    attr.send_cq = send_cq;
    attr.recv_cq = NULL; // intentionally left NULL

    struct ibv_qp *qp = ibv_create_qp(pd, &attr);
    if (!qp) { perror("ibv_create_qp"); return 0; }
    return 0;
}
```

**Compilation and run with ASan**:
```bash
gcc -O1 -g -fsanitize=address -fno-omit-frame-pointer \
    poc.c -o poc -libverbs

export ASAN_OPTIONS='abort_on_error=1,fast_unwind_on_malloc=0,detect_leaks=1'
export ASAN_SYMBOLIZER_PATH=$(command -v llvm-symbolizer || true)

./poc
```

**ASan report (excerpt)**:
```
AddressSanitizer:DEADLYSIGNAL
=================================================================
==1199856==ERROR: AddressSanitizer: SEGV on unknown address 0x000000000018 (pc 0x7e56fecf0a17 bp 0x7fffebdebd50 sp 0x7fffebdebad0 T0)
==1199856==The signal is caused by a READ memory access.
==1199856==Hint: address points to the zero page.
    #0 0x7e56fecf0a17 in ibv_icmd_create_qp libibverbs/cmd_qp.c:140
    #1 0x7e56fecf2b7d in ibv_cmd_create_qp libibverbs/cmd_qp.c:394
    #2 0x7e56fe0ce6fa  (/usr/lib/x86_64-linux-gnu/libibverbs/librxe-rdmav34.so+0x46fa)
    #3 0x57435dc2559a in main /home/user/rdma/poc.c:23
    #4 0x7e56fde29d8f in __libc_start_call_main ../sysdeps/nptl/libc_start_call_main.h:58
    #5 0x7e56fde29e3f in __libc_start_main_impl ../csu/libc-start.c:392
    #6 0x57435dc25264 in _start (/home/user/rdma/poc+0x1264)

AddressSanitizer can not provide additional info.
SUMMARY: AddressSanitizer: SEGV libibverbs/cmd_qp.c:140 in ibv_icmd_create_qp
==1199856==ABORTING
[1]    1199856 IOT instruction (core dumped)  ./poc
```

**Analysis:**
- In `ibv_icmd_create_qp()` (`libibverbs/cmd_qp.c`), the `non-IND_TABLE`
branch unconditionally dereferences `attr_ex->recv_cq->handle`.
- In contrast, the `IND_TABLE` branch explicitly checks for illegal combinations
of `recv_cq/srq/max_recv_wr/max_recv_sge`.
- This asymmetry means that a NULL `recv_cq` leads to SIGSEGV instead of a
controlled error.
- The issue still exists in current `rdma-core` (see https://github.com/linux-rdma/rdma-core, 5df6832)

**Proposed fix**:
Add `NULL` checks for both `send_cq` and `recv_cq` in the `non-IND_TABLE` branch,
returning `EINVAL` if they are not set.

```diff
From a39bea23c9472e87060680e2384960434ec86808 Mon Sep 17 00:00:00 2001
From: Liuyi <asatsuyu.liu@gmail.com>
Date: Mon, 15 Sep 2025 11:23:15 +0800
Subject: [PATCH] libibverbs: validate send_cq/recv_cq in non-IND_TABLE path

---
 libibverbs/cmd_qp.c | 9 +++++++++
 1 file changed, 9 insertions(+)

diff --git a/libibverbs/cmd_qp.c b/libibverbs/cmd_qp.c
index 499b241e5..c40553782 100644
--- a/libibverbs/cmd_qp.c
+++ b/libibverbs/cmd_qp.c
@@ -132,11 +132,20 @@ static int ibv_icmd_create_qp(struct ibv_context *context,
 				send_cq_handle = attr_ex->send_cq->handle;
 			}
 		} else {
+			if (!attr_ex->send_cq) {
+				errno = EINVAL;
+				return errno;
+			}
+
 			fill_attr_in_obj(cmdb, UVERBS_ATTR_CREATE_QP_SEND_CQ_HANDLE,
 				 attr_ex->send_cq->handle);
 			send_cq_handle = attr_ex->send_cq->handle;
 
 			if (attr_ex->qp_type != IBV_QPT_XRC_SEND) {
+				if (!attr_ex->recv_cq) {
+					errno = EINVAL;
+					return errno;
+				}
 				fill_attr_in_obj(cmdb, UVERBS_ATTR_CREATE_QP_RECV_CQ_HANDLE,
 						 attr_ex->recv_cq->handle);
 				recv_cq_handle = attr_ex->recv_cq->handle;
-- 
2.34.1

```

**Security consideration**:
This is primarily a robustness bug. In environments where applications may be
driven by untrusted inputs (e.g. fuzzing frameworks, multi-tenant clusters),
it could be considered a denial-of-service vulnerability.
Please advise whether this should be treated as CVE-worthy or just a
robustness fix.

Thanks for your attention!

Best regards,

Yi Liu
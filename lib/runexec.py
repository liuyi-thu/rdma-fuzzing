from __future__ import annotations

import json
import os.path
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import random

from lib import utils
from lib.auto_run import run_once
from lib.finder_print import FingerprintManager

FP_MANAGER = FingerprintManager()

def feed_back():
    utils.run_cmd("rm -f /home/user_coverage.json")
    utils.run_cmd("rm -f /home/kernel_coverage.json")

    user_cmd = "python3 /home/fastcov/fastcov.py -f /home/rdma-core-master/build/librdmacm/CMakeFiles/rspreload.dir/*.gcda /home/rdma-core-master/build/libibverbs/CMakeFiles/ibverbs.dir/*.gcda /home/rdma-core-master/build/librdmacm/CMakeFiles/rdmacm.dir/*.gcda -e /home/rdma-core-master/build/include -o /home/user_coverage.json -X"
    for i in range(5):
        utils.run_cmd(user_cmd)
        if (utils.retry_until_file_exist("/home/user_coverage.json")):
            print("[+] User coverage generated successfully")
            break
        else:
            print("[-] /home/user_coverage.json not found, retrying...")

    kernel_cmd = "python3 /home/fastcov/fastcov.py -f /sys/kernel/debug/gcov/home/lbz/qemu/noble/drivers/infiniband/core/*.gcda /sys/kernel/debug/gcov/home/lbz/qemu/noble/drivers/infiniband/sw/rxe/*.gcda -i /home/lbz/qemu/noble/drivers/infiniband/ -o /home/kernel_coverage.json -X"
    for i in range(5):
        utils.run_cmd(kernel_cmd)
        if (utils.retry_until_file_exist("/home/kernel_coverage.json")):
            print("[+] Kernel coverage generated successfully")
            break
        else:
            print("[-] /home/kernel_coverage.json not found, retrying...")

    if os.path.exists("/home/user_coverage.json") and os.path.exists("/home/kernel_coverage.json"):
        all_edges = collect_all_edges("/home/user_coverage.json", "/home/kernel_coverage.json")
        print(f"[+] Coverage collection done, edges: {len(all_edges)}")
        return all_edges
    else:
        print("[-] Error")
        return set()

def collect_all_edges(user_json: str, kernel_json: str) -> set[str]:
    edges = set()
    if os.path.exists(user_json):
        edges |= parse_fastgcov_edges(user_json)   # 并集
    if os.path.exists(kernel_json):
        edges |= parse_fastgcov_edges(kernel_json)
    return edges

def parse_fastgcov_edges(json_path: str) -> set[str]:
    with open(json_path) as f:
        data = json.load(f)

    edges = set()
    for file_path, file_data in data.get("sources", {}).items():
        for unit_name, unit_data in file_data.items():
            lines = unit_data.get("lines", {})
            for lineno, count in lines.items():
                if count > 0:
                    edges.add(f"{file_path}:{lineno}")
    return edges


def extract_sem_signature(log_path: str) -> set[str]:
    sem_signature = set()
    seen_indices = set()

    pattern = re.compile(r'^\[(\d+)\]\s*(.+?)\s+start\.$')

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            m = pattern.match(line)
            if not m:
                continue
            idx = int(m.group(1))
            if idx in seen_indices:
                continue
            seen_indices.add(idx)

            action = m.group(2)
            sem_signature.add(action)

    return sem_signature

def parse_crash_site(log_path: str) -> Optional[str]:
    SUMMARY_RE = re.compile(r'^SUMMARY: AddressSanitizer: \S+ (\S+):(\d+) in')
    FRAME_SRC_RE = re.compile(r'^\s*#\d+\s+\S+\s+in\s+\S+\s+(/[^:]+):(\d+)')
    FRAME_MODULE_RE = re.compile(r'\(([^)]+)\+0x([0-9a-fA-F]+)\)')
    log_text = ""
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        log_text = f.read()
    if "AddressSanitizer" not in log_text and "Address" not in log_text:
        return None
    for line in log_text.splitlines():
        m = SUMMARY_RE.search(line)
        if m:
            filepath, lineno = m.group(1), m.group(2)
            lib = Path(filepath).name
            return f"bt#{lib}+{lineno}"
    for line in log_text.splitlines():
        m = FRAME_SRC_RE.search(line)
        if m:
            filepath, lineno = m.group(1), m.group(2)
            lib = Path(filepath).name
            return f"bt#{lib}+{lineno}"
    for line in log_text.splitlines():
        m = FRAME_MODULE_RE.search(line)
        if m:
            module_path, offset = m.group(1), m.group(2)
            module_name = Path(module_path).name
            return f"bt#{module_name}+0x{offset}"

    return None

# ========== 需要你接到现有实现的钩子 ==========


def build_and_run() -> Dict[str, Any]:
    """编译 & 执行 verbs 序列，并返回一次性原始指标。
    期望返回：
    {
      'outcome': 'ok' | 'crash' | 'asan' | 'error',
      'runtime_ms': 123,
      'coverage_edges': set([...]) 或 可哈希摘要（bytes/str），
      'sem_signature': set([...]) 或 可哈希摘要（bytes/str），
      'crash_site': 'bt#lib+offset' | None,
    }
    """
    # TODO: 接你现有执行流程（你已有的 codegen/runner/trace 收集）
    t0 = time.time()

    run_once()
    print("[+] run_once finished")
    coverage_edges = feed_back()
    sem_signature = extract_sem_signature("./repo/client.tmp.stdout.log")
    print(f"[+] Extracted sem_signature, count={len(sem_signature)}")
    crash_site = parse_crash_site("./repo/client.tmp.stderr.log")
    if not crash_site:
        outcome = "ok"
        print("[+] No crash detected")
    else:
        outcome = "crash"
        print(f"[!] Crash detected, site: {crash_site}")

    return {
        "outcome": outcome,
        "runtime_ms": int((time.time() - t0) * 1000),
        "coverage_edges": coverage_edges,
        "sem_signature": sem_signature,
        "crash_site": crash_site,
    }

def diff_coverage_and_semantics(new_cov, new_sem) -> Dict[str, int]:
    cov_new, sem_new = FP_MANAGER.diff(new_cov, new_sem)
    return {"cov_new": cov_new, "sem_new": sem_new}

# ============================================


def compute_score(cov_new: int, sem_new: int, outcome: str, runtime_ms: int, flaky_rate: float = 0.0) -> float:
    w_cov, w_sem, w_crash, w_flaky, w_slow = 1.0, 0.2, 3.0, 2.0, 0.0005
    crash_bonus = {"asan": 1.0, "crash": 0.6, "error": 0.2}.get(outcome, 0.0)
    score = w_cov * cov_new + w_sem * sem_new + w_crash * crash_bonus
    score -= w_flaky * flaky_rate
    score -= w_slow * max(runtime_ms - 200, 0) * w_slow  # 200ms 以上轻度降权
    return max(score, 0.0)


def execute_and_collect() -> Dict[str, Any]:
    print("[+] Collecting fuzz execution metrics")
    raw = build_and_run()
    diff = diff_coverage_and_semantics(raw.get("coverage_edges", set()),
                                       raw.get("sem_signature", set()))
    cov_new = diff["cov_new"]
    sem_new = diff["sem_new"]
    print(f"[+] Coverage delta: {cov_new}, Semantic delta: {sem_new}")
    # cov_new = diff_coverage_and_semantics(raw.get("coverage_edges"), raw.get("sem_signature"))["cov_new"]
    # sem_new = diff_coverage_and_semantics(raw.get("coverage_edges"), raw.get("sem_signature"))["sem_new"]
    # score = compute_score(cov_new, sem_new, raw.get("outcome", "ok"), int(raw.get("runtime_ms", 0)))
    # score = random.uniform(0, 1)  # 暂时用一个随机数
    # cov_new = 0
    # sem_new = 0

    # keep = (cov_new > 0) or (sem_new > 0) or (raw.get("outcome") in ("asan", "crash"))
    # keep = True  # 暂时全部保留，方便调试
    score = compute_score(cov_new, sem_new, raw.get("outcome", "ok"),
                          int(raw.get("runtime_ms", 0)))
    print(f"[+] Computed score: {score:.3f}")

    keep = (cov_new > 0) or (sem_new > 0) or (raw.get("outcome") in ("asan", "crash"))
    if keep:
        print("[+] Keep this input (valuable)")
    else:
        print("[-] Discard this input (no novelty)")
    return {
        "keep": keep,
        "outcome": raw.get("outcome"),
        "cov_new": cov_new,
        "sem_novelty": float(sem_new),
        "runtime_ms": int(raw.get("runtime_ms", 0)),
        "crash_site": raw.get("crash_site"),
        "score": score,
        "detail": raw,
    }

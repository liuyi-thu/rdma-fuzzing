from __future__ import annotations
import time
from typing import Any, Dict, List
import random

# ========== 需要你接到现有实现的钩子 ==========


def build_and_run(verbs: List[Any]) -> Dict[str, Any]:
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
    # ...
    # 占位：没有真实执行时，返回一个假结果
    return {
        "outcome": "ok",
        "runtime_ms": int((time.time() - t0) * 1000),
        "coverage_edges": [],
        "sem_signature": [],
        "crash_site": None,
    }


def diff_coverage_and_semantics(new_cov, new_sem) -> Dict[str, int]:
    """与全局/历史指纹比较，得到此次新增的规模。这里做一个简化占位。"""
    # TODO: 替换为你真实的全局集合/位图比较
    return {
        "cov_new": len(new_cov) if isinstance(new_cov, set) else 0,
        "sem_new": len(new_sem) if isinstance(new_sem, set) else 0,
    }


# ============================================


def compute_score(cov_new: int, sem_new: int, outcome: str, runtime_ms: int, flaky_rate: float = 0.0) -> float:
    w_cov, w_sem, w_crash, w_flaky, w_slow = 1.0, 0.7, 3.0, 2.0, 0.0005
    crash_bonus = {"asan": 1.0, "crash": 0.6, "error": 0.2}.get(outcome, 0.0)
    score = w_cov * cov_new + w_sem * sem_new + w_crash * crash_bonus
    score -= w_flaky * flaky_rate
    score -= w_slow * max(runtime_ms - 200, 0) * w_slow  # 200ms 以上轻度降权
    return max(score, 0.0)


def execute_and_collect(verbs: List[Any]) -> Dict[str, Any]:
    raw = build_and_run(verbs)
    # cov_new = diff_coverage_and_semantics(raw.get("coverage_edges"), raw.get("sem_signature"))["cov_new"]
    # sem_new = diff_coverage_and_semantics(raw.get("coverage_edges"), raw.get("sem_signature"))["sem_new"]
    # score = compute_score(cov_new, sem_new, raw.get("outcome", "ok"), int(raw.get("runtime_ms", 0)))
    score = random.uniform(0, 1)  # 暂时用一个随机数
    cov_new = 0
    sem_new = 0

    # keep = (cov_new > 0) or (sem_new > 0) or (raw.get("outcome") in ("asan", "crash"))
    keep = True  # 暂时全部保留，方便调试
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

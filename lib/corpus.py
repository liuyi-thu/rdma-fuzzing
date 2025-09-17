# lib/corpus.py
# -*- coding: utf-8 -*-
"""
Corpus 管理：
- 以 SQLite + seeds/ 目录持久化
- 规范化 IR + 稳定哈希 去重
- 记录运行结果与综合得分，用于调度

依赖：标准库 + dill（可选：已在项目中使用）
"""

from __future__ import annotations
import os
import json
import time
import sqlite3
import hashlib
import zlib
import random
from dataclasses import is_dataclass, asdict
from typing import Any, Dict, List, Optional

try:
    import dill  # 更好地序列化 Python 对象
except ImportError:  # 允许无 dill 的退化存档
    dill = None


class Corpus:
    DB_NAME = "corpus.db"

    def __init__(self, root: str):
        self.root = root
        self.seed_dir = os.path.join(root, "seeds")
        os.makedirs(self.seed_dir, exist_ok=True)
        self.db_path = os.path.join(root, self.DB_NAME)
        self.db = sqlite3.connect(self.db_path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    # ----------------------------- schema -----------------------------
    def _init_schema(self):
        cur = self.db.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS seeds (
                id TEXT PRIMARY KEY,
                added_at INTEGER,
                last_used_at INTEGER,
                cov_bits_new INTEGER DEFAULT 0,
                sem_novelty REAL DEFAULT 0.0,
                crash_kind TEXT,
                crash_site TEXT,
                flaky_rate REAL DEFAULT 0.0,
                runtime_ms_mean REAL DEFAULT 0.0,
                runtime_ms_p95 REAL DEFAULT 0.0,
                score REAL DEFAULT 0.0
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                seed_id TEXT,
                time INTEGER,
                outcome TEXT,
                cov_delta INTEGER,
                runtime_ms INTEGER,
                detail_json TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
                k TEXT PRIMARY KEY,
                v TEXT
            );
            """
        )
        self.db.commit()

    # ----------------------------- utils ------------------------------
    @staticmethod
    def _safe_primitive(v: Any) -> Any:
        """尽量转为 hash/JSON 稳定的基本类型。"""
        if v is None:
            return None
        if isinstance(v, (bool, int, float, str)):
            return v
        if isinstance(v, (bytes, bytearray)):
            # 对大块二进制做短哈希，避免把不稳定内容写进 IR
            h = hashlib.sha256(v).hexdigest()[:16]
            return {"__bytes_hash__": h, "len": len(v)}
        if isinstance(v, (list, tuple)):
            return [Corpus._safe_primitive(x) for x in v]
        if isinstance(v, dict):
            return {str(k): Corpus._safe_primitive(v[k]) for k in sorted(v.keys(), key=str)}
        if is_dataclass(v):
            return Corpus._safe_primitive(asdict(v))
        # 尝试通用 to_norm / to_dict
        for meth in ("to_norm", "to_dict"):
            if hasattr(v, meth) and callable(getattr(v, meth)):
                try:
                    return Corpus._safe_primitive(getattr(v, meth)())
                except Exception:
                    pass
        # 兜底：repr 的稳定性较差，但可作为最后方案
        return {"__repr__": repr(v)}

    @staticmethod
    def normalize_ir(verbs: List[Any]) -> Dict[str, Any]:
        def norm_one(v: Any) -> Dict[str, Any]:
            name = getattr(v, "__class__").__name__
            # 优先使用 get_mutable_params() 暴露的字段；否则回退到 __dict__
            params = {}
            if hasattr(v, "get_mutable_params"):
                try:
                    mp = v.get_mutable_params()  # 期望: dict-like
                except Exception:
                    mp = {}
                for k, val in (mp or {}).items():
                    params[k] = Corpus._safe_primitive(val)
            else:
                for k, val in sorted(getattr(v, "__dict__", {}).items()):
                    if k.startswith("_"):
                        continue
                    params[k] = Corpus._safe_primitive(val)
            return {"name": name, "params": params}

        return {"seq": [norm_one(v) for v in verbs]}

    @staticmethod
    def seed_hash(ir: Dict[str, Any]) -> str:
        b = json.dumps(ir, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(b).hexdigest()

    # ----------------------------- IO ------------------------------
    def _seed_paths(self, sid: str) -> Dict[str, str]:
        return {
            "ir": os.path.join(self.seed_dir, f"{sid}.json"),
            "meta": os.path.join(self.seed_dir, f"{sid}.meta.json"),
            "obj": os.path.join(self.seed_dir, f"{sid}.dill"),
        }

    def add(self, verbs: List[Any], meta: Optional[Dict[str, Any]] = None) -> str:
        ir = self.normalize_ir(verbs)
        sid = self.seed_hash(ir)
        paths = self._seed_paths(sid)

        # 写 IR / meta / 对象
        if not os.path.exists(paths["ir"]):
            with open(paths["ir"], "w", encoding="utf-8") as f:
                json.dump(ir, f, ensure_ascii=False, indent=2)
        if meta is None:
            meta = {}
        with open(paths["meta"], "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        if dill is not None:
            with open(paths["obj"], "wb") as f:
                dill.dump(verbs, f)

        # 入库（若已存在则 ignore）
        cur = self.db.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO seeds(id, added_at, last_used_at, cov_bits_new, sem_novelty) VALUES (?,?,?,?,?)",
            (
                sid,
                int(time.time()),
                int(time.time()),
                int(meta.get("cov_bits_new", 0)),
                float(meta.get("sem_novelty", 0.0)),
            ),
        )
        self.db.commit()
        return sid

    def load_verbs(self, sid: str) -> Optional[List[Any]]:
        paths = self._seed_paths(sid)
        if dill is None or not os.path.exists(paths["obj"]):
            return None
        try:
            import dill as _d

            return _d.load(open(paths["obj"], "rb"))
        except Exception:
            return None

    def record_run(self, sid: str, run: Dict[str, Any]):
        cur = self.db.cursor()
        print(run)
        cur.execute(
            "INSERT INTO runs(seed_id, time, outcome, cov_delta, runtime_ms, detail_json) VALUES (?,?,?,?,?,?)",
            (
                sid,
                int(time.time()),
                str(run.get("outcome")),
                int(run.get("cov_delta", 0)),
                int(run.get("runtime_ms", 0)),
                json.dumps(run, ensure_ascii=False),
            ),
        )
        # 更新 seeds 表：
        score = float(run.get("score", 0.0))
        cur.execute(
            "UPDATE seeds SET last_used_at=?, cov_bits_new=MAX(cov_bits_new, ?), score=? WHERE id=?",
            (int(time.time()), int(run.get("cov_delta", 0)), score, sid),
        )
        self.db.commit()

    # ----------------------------- 调度 -----------------------------
    def pick_for_fuzz(self) -> Optional[str]:
        """按 score 排序 + 温度采样。若库空，返回 None。"""
        cur = self.db.cursor()
        cur.execute("SELECT id, score FROM seeds ORDER BY score DESC LIMIT 64")
        rows = cur.fetchall()
        if not rows:
            return None
        ids = [r[0] for r in rows]
        ws = [max(float(r[1]), 0.0) + 1e-3 for r in rows]
        return random.choices(ids, weights=ws, k=1)[0]

    # ----------------------------- 全局状态 -----------------------------
    def get_global_cov_fingerprint(self) -> str:
        """可选：维护全局覆盖位的压缩摘要（便于快速比较）。"""
        cur = self.db.cursor()
        cur.execute("SELECT v FROM kv WHERE k='global_cov'")
        row = cur.fetchone()
        return row[0] if row else ""

    def set_global_cov_fingerprint(self, blob: bytes):
        cur = self.db.cursor()
        cur.execute("REPLACE INTO kv(k, v) VALUES ('global_cov', ?)", (zlib.compress(blob).hex(),))
        self.db.commit()

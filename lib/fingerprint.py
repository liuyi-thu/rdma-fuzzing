import hashlib
from typing import Set, Iterable, Tuple

class FingerprintManager:
    def __init__(self):
        self.cov_hashes: Set[int] = set()
        self.sem_hashes: Set[int] = set()

    @staticmethod
    def hash_item(item: str) -> int:
        h = hashlib.sha256(item.encode("utf-8")).digest()
        return int.from_bytes(h[:8], "little")  # 取前 8 字节做哈希值

    def update_coverage(self, edges: Iterable[str]) -> int:
        new_count = 0
        for edge in edges:
            h = self.hash_item(edge)
            if h not in self.cov_hashes:
                self.cov_hashes.add(h)
                new_count += 1
        return new_count

    def update_semantics(self, sems: Iterable[str]) -> int:
        new_count = 0
        for sig in sems:
            h = self.hash_item(sig)
            if h not in self.sem_hashes:
                self.sem_hashes.add(h)
                new_count += 1
        return new_count

    def diff(self, edges: Iterable[str], sems: Iterable[str]) -> Tuple[int, int]:
        cov_new = self.update_coverage(edges)
        sem_new = self.update_semantics(sems)
        return cov_new, sem_new

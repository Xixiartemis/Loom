"""DuplicateDetector + ExpirationValidator(docs/11:去重与失效判断,确定性)。"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from lhas.job.models import JobRecord


class ExpirationValidator:
    """按基准日期判断岗位是否过期:expires_at < as_of → EXPIRED。

    基准日期默认取数据集 manifest 的 as_of_date/created_at,保证锁定数据集
    的判定可复现,不随运行当天漂移。
    """

    def __init__(self, as_of: Optional[date] = None):
        self.as_of = as_of or date.today()

    def check(self, job: JobRecord) -> str:
        expires = job.expires_date
        if expires is None:
            return "ACTIVE"
        return "EXPIRED" if expires < self.as_of else "ACTIVE"


def _normalize_company(name: str) -> str:
    return re.sub(r"(有限公司|科技|股份|集团|\(.*?\)|（.*?）)", "", name).strip()


def _normalize_title(title: str) -> str:
    return re.sub(r"\(.*?\)|（.*?）|二次发布", "", title).strip()


class DuplicateDetector:
    """基于 公司+标题 规范化与 requirements 词集 Jaccard 的确定性去重。

    Jaccard >= threshold 且公司/标题规范化后相同 → 判定为重复组。
    """

    def __init__(self, jobs: list[JobRecord], threshold: float = 0.8):
        self.jobs = jobs
        self.threshold = threshold

    @staticmethod
    def _req_set(job: JobRecord) -> set[str]:
        words: set[str] = set()
        for r in job.requirements:
            for token in re.split(r"[/、,，;；()（）\s]+", r):
                token = token.strip()
                if token and len(token) >= 2:
                    words.add(token)
        return words

    def _similarity(self, a: JobRecord, b: JobRecord) -> float:
        sa, sb = self._req_set(a), self._req_set(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def find_duplicate_pairs(self) -> list[tuple[str, str, float]]:
        pairs: list[tuple[str, str, float]] = []
        for i in range(len(self.jobs)):
            for j in range(i + 1, len(self.jobs)):
                a, b = self.jobs[i], self.jobs[j]
                if _normalize_company(a.company) != _normalize_company(b.company):
                    continue
                if _normalize_title(a.title) != _normalize_title(b.title):
                    continue
                sim = self._similarity(a, b)
                if sim >= self.threshold:
                    pairs.append((a.job_id, b.job_id, round(sim, 3)))
        return pairs

    def groups(self) -> dict[str, list[str]]:
        """duplicate_group -> [job_ids]。"""
        out: dict[str, list[str]] = {}
        for a, b, _ in self.find_duplicate_pairs():
            key = f"dup-{a}"
            out.setdefault(key, []).extend([a, b])
        for key in out:
            out[key] = sorted(set(out[key]))
        return out

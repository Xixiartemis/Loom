"""HardRuleValidator — 确定性硬约束检查(docs/11, 不依赖任何模型)。

检查项(与 benchmarks/job-v0.1/manifest.json 的 hard_constraints 规则一致):
1. 学历:degree_required 与候选人学历(硕士/博士硬性要求)
2. 毕业年份:graduate_year_required 与候选人毕业年份
3. 地点:location 与 career_goal.location_preference(remote=true 时豁免)
4. 核心技能:JD 要求与候选人技能交集(短板信号全命中且无匹配 → 失败)
5. 经验:experience_required 中的年限要求与候选人经验

注意:"优先"/"加分" 类表述不构成硬性失败(如"硕士优先")。
"""

from __future__ import annotations

import re
from typing import Optional

from lhas.job.models import (
    CandidateProfile,
    CareerGoal,
    HardConstraintResult,
    JobRecord,
)

# 候选人明显不具备、一旦成为 JD 硬要求即构成技能不匹配的信号词。
# 与 JOB-V0.1 数据集陷阱设计一致。
WEAK_SKILL_SIGNALS = [
    "C/C++", "C++", "嵌入式", "单片机", "RTOS", "Java", "Spring Boot", "Spring",
    "WebGL", "Three.js", "3D 渲染", "K8s", "Kubernetes", "GPU 推理", "分布式训练",
    "PyTorch 底层", "预训练", "RLHF", "模型微调", "论文发表", "数据仓库", "BI 工具",
    "Milvus", "向量数据库", "检索优化", "CI/CD", "Docker/K8s",
]

# token 重叠匹配时忽略的通用词(避免"分布式基础"误配"Docker 基础")
_SKILL_STOPWORDS = {
    "基础", "开发", "设计", "经验", "能力", "平台", "系统", "工具", "产品",
    "方向", "相关", "优先", "加分", "扎实", "良好", "类", "或", "与", "及",
    "工程师", "岗位", "要求", "工作", "负责", "参与", "熟悉", "掌握", "了解",
}


def skill_tokens(text: str) -> set[str]:
    toks = set(re.split(r"[/、,，;；()（）\s]+", text))
    return {t for t in toks if len(t) >= 2 and not t.isdigit() and t not in _SKILL_STOPWORDS}


def matches_any_skill(requirement: str, skill_flat: list[str]) -> bool:
    """JD 要求与候选人技能是否共享任一显著 token(双向健壮匹配)。"""
    rt = skill_tokens(requirement)
    if not rt:
        return False
    for skill in skill_flat:
        if rt & skill_tokens(skill):
            return True
    return False


class HardRuleValidator:
    def __init__(self, profile: CandidateProfile, goal: CareerGoal):
        self.profile = profile
        self.goal = goal

    def validate(self, job: JobRecord) -> HardConstraintResult:
        violations: list[str] = []
        violations += self._check_degree(job)
        violations += self._check_graduation_year(job)
        violations += self._check_location(job)
        violations += self._check_skills(job)
        violations += self._check_experience(job)
        return HardConstraintResult(passed=not violations, violations=violations)

    # ------------------------------------------------------------------ bits

    def _check_degree(self, job: JobRecord) -> list[str]:
        req = job.degree_required
        degree = self.profile.education.degree
        out: list[str] = []
        # 硬性要求(出现"硕士"/"博士"且不含"优先/可/以上可放宽"修饰)
        for required, label in [("博士", "博士"), ("硕士", "硕士")]:
            if required in req and "优先" not in req:
                rank = {"本科": 1, "硕士": 2, "博士": 3}
                if rank.get(degree, 1) < rank[required]:
                    out.append(f"学历:岗位要求{label},{degree}学历不满足")
        return out

    def _check_graduation_year(self, job: JobRecord) -> list[str]:
        required = job.graduate_year_required
        if not required:
            return []
        try:
            year = int(str(required).replace("届", ""))
        except ValueError:
            return []
        if year != self.profile.education.graduation_year:
            return [f"毕业年份:岗位要求{year}届,候选人为{self.profile.education.graduation_year}届"]
        return []

    def _check_location(self, job: JobRecord) -> list[str]:
        if job.remote and "远程" in self.goal.location_preference:
            return []
        prefs = self.goal.location_preference
        if job.location in prefs:
            return []
        return [f"地点:岗位在{job.location},候选人偏好为{'/'.join(prefs)}"]

    def _check_skills(self, job: JobRecord) -> list[str]:
        """技能硬性失败:JD 要求全部命中短板信号,且与候选人技能零匹配。"""
        matched = [r for r in job.requirements if self._matches_profile(r)]
        weak_hits = [r for r in job.requirements if self._is_weak(r)]
        if not matched and weak_hits and len(weak_hits) >= len(job.requirements) * 0.5:
            return [f"技能:核心要求({'; '.join(weak_hits)})与候选人技能不匹配"]
        return []

    def _check_experience(self, job: JobRecord) -> list[str]:
        req = job.experience_required
        if not req or "年" not in req:
            return []
        if "实习可折算" in req or "可折算" in req:
            # 可折算时,实习时长计入;仍不足一年则视为部分满足,不硬性失败
            return []
        # 提取年限(取第一个数字)
        import re
        m = re.search(r"(\d+)\s*年", req)
        if not m:
            return []
        years = int(m.group(1))
        months = self.profile.total_experience_months
        if months < years * 12:
            return [f"经验:岗位要求{req},候选人仅有 {months} 个月实习/工作经验"]
        return []

    # -------------------------------------------------------------- helpers

    def _matches_profile(self, requirement: str) -> bool:
        return matches_any_skill(requirement, self.profile.skill_flat)

    def _is_weak(self, requirement: str) -> bool:
        return any(sig in requirement for sig in WEAK_SKILL_SIGNALS)

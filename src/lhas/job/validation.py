"""JobMatchValidator — Job 场景的 ValidationPolicy(Phase B Validator 协议实现)。

判断"预测是否可信",为 EXP-JOB-002 的 Recovery 实验提供 FAIL 信号:
- 预测声称 hard pass 但确定性规则判定 hard fail → 验证失败(证据冲突)
- fit=HIGH 但方向与 career goal 冲突(avoid 方向 / target 外)→ 验证失败
- should_apply=true 但岗位已过期 → 验证失败

Validator 只判断,不修改预测。确定性优先,不依赖 LLM。
"""

from __future__ import annotations

from lhas.job.detectors import ExpirationValidator
from lhas.job.matching import RuleBasedMatcher
from lhas.job.models import JobDataset, MatchPrediction
from lhas.validation import ValidationCheck, ValidationResult


class JobMatchValidator:
    """V1/V2 级 Job 验证:硬约束一致性 + 方向冲突 + 过期检查。"""

    def __init__(self, dataset: JobDataset, as_of=None):
        self.dataset = dataset
        self._hard = RuleBasedMatcher(dataset.profile, dataset.goal)
        self._expiration = ExpirationValidator(as_of=as_of or dataset.as_of_date)

    def validate(self, prediction: MatchPrediction) -> ValidationResult:
        job = self.dataset.jobs[prediction.job_id]
        gt = self.dataset.labels[prediction.job_id]
        checks: list[ValidationCheck] = []

        # V2 rule: 硬约束一致性(与确定性规则比对,不信任模型自称)
        rule_hard = self._hard._hard.validate(job)  # noqa: SLF001 — 复用规则检查
        checks.append(ValidationCheck(
            name="hard_constraints_consistent",
            passed=prediction.hard_constraints_pass == rule_hard.passed,
            detail=f"prediction={prediction.hard_constraints_pass} rule={rule_hard.passed} {rule_hard.violations}"
            if prediction.hard_constraints_pass != rule_hard.passed else None,
        ))

        # V2 rule: 方向冲突(fit=HIGH 但方向不匹配 career goal)
        direction = RuleBasedMatcher(self.dataset.profile, self.dataset.goal)._direction(job)
        if prediction.fit == "HIGH" and direction < 1.0:
            checks.append(ValidationCheck(
                name="direction_conflict",
                passed=False,
                detail=f"fit=HIGH but direction={direction} vs career goal targets={self.dataset.goal.target_roles}",
            ))
        else:
            checks.append(ValidationCheck(name="direction_conflict", passed=True))

        # V2 rule: 过期岗位不得 should_apply
        expired = self._expiration.check(job) == "EXPIRED"
        if prediction.should_apply and expired:
            checks.append(ValidationCheck(
                name="expired_apply",
                passed=False,
                detail=f"job {job.job_id} expired but should_apply=true",
            ))
        else:
            checks.append(ValidationCheck(name="expired_apply", passed=True))

        # V1 structural: 输出结构完整
        structure_ok = prediction.fit in ("HIGH", "MEDIUM", "LOW") and 0 <= prediction.score <= 100
        checks.append(ValidationCheck(name="structure", passed=structure_ok))

        passed = all(c.passed for c in checks)
        evidence = "; ".join(
            f"{c.name}: {'ok' if c.passed else 'FAIL - ' + (c.detail or '')}" for c in checks
        )
        return ValidationResult(
            attempt_id=prediction.job_id,
            passed=passed,
            checks=checks,
            evidence=evidence,
        )

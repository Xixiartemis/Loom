# Eval Protocol

## Eval 目标
评测 LHAS 是否：
- 更有效
- 更稳定
- 更省人工
- 更高效
- 更可解释
- 更可复现

## 六类核心指标

### A. Effectiveness
- Task Success Rate
- First Pass Success Rate
- Final Success Rate
- Recovery Success Rate

Recovery Success 定义：
> 首次 Attempt 失败，但没有人工修改核心结果，系统通过 Recovery 最终完成 Task。

### B. Reliability
- executor_crash_rate
- timeout_rate
- validation_failure_rate
- unknown_failure_rate
- regression_rate

### C. Efficiency
- attempt_count
- wall_clock_time
- executor_time
- validation_time
- tool_calls
- input_tokens
- output_tokens
- estimated_cost

### D. Autonomy
- human_intervention_count
- human_intervention_rate

类型：
- NONE
- TASK_CLARIFICATION
- ENVIRONMENT_FIX
- MANUAL_CONTEXT_SUPPLY
- MANUAL_RECOVERY
- MANUAL_CODE_FIX
- HUMAN_APPROVAL

### E. Context Efficiency
- context_size
- context_tokens
- files_or_sources_supplied
- failure_context_size
- recovery_context_delta

### F. Quality

Job Benchmark：
- hard_constraint_accuracy
- fit_classification_accuracy
- precision_at_5
- recall_at_10
- ranking_quality
- evidence_accuracy
- hallucination_rate
- duplicate_detection_rate
- expired_job_detection_rate
- human_acceptance_rate

SWE Benchmark：
- tests_pass
- regression_pass
- lint_pass
- typecheck_pass
- acceptance_pass

## 正式结论要求
允许：
> CP-2 在当前 Dataset 上提高了 Recovery Success，但平均 Context Token 上升。

禁止：
> 新 Harness 更聪明。

除非有可靠指标支持。

# Logging & Trace Spec

## 原则
每一次正式 Run 都必须能完整重放“发生了什么”。

## Experiment 目录
```text
experiments/
└── EXP-xxxx/
    ├── experiment.json
    ├── summary.md
    ├── config/
    │   ├── executor.json
    │   ├── harness.json
    │   └── environment.json
    └── tasks/
        └── TASK-001/
            ├── task.yaml
            ├── result.json
            ├── timeline.jsonl
            └── runs/
                └── attempt-01/
                    ├── context.json
                    ├── context.md
                    ├── executor-result.json
                    ├── executor-events.jsonl
                    ├── stdout.log
                    ├── stderr.log
                    ├── artifacts.json
                    ├── validation.json
                    ├── failure.json
                    ├── recovery.json
                    └── usage.json
```

SWE Benchmark 可额外保存：
- git-diff.patch
- final-diff.patch

Job Benchmark 可额外保存：
- job-results.json
- ranking.json
- application-draft.json
- sources.json

## Event 基本结构
```json
{
  "sequence": 12,
  "task_id": "TASK-001",
  "run_id": "RUN-001",
  "attempt_id": "ATT-002",
  "type": "VALIDATION_FAILED",
  "timestamp": "...",
  "payload": {}
}
```

## Event Type(以代码实现为准,2026-08-18 回写)

原则：**每个关键状态迁移产生 Event**。以下目录与 `src/lhas/domain/enums.py`
保持一致;实现扩展新事件时,必须同步回写本文档。

### Task 生命周期
- TASK_CREATED
- TASK_STARTED
- TASK_COMPLETED
- TASK_FAILED
- TASK_ESCALATED
- TASK_CANCELLED

### Run 生命周期
- RUN_CREATED
- RUN_STARTED
- RUN_COMPLETED
- RUN_FAILED
- RUN_ESCALATED

### Attempt 生命周期
- ATTEMPT_STARTED
- ATTEMPT_COMPLETED
- ATTEMPT_FAILED
- ATTEMPT_TIMED_OUT
- ATTEMPT_CRASHED

### Context
- CONTEXT_BUILT

### Executor
- EXECUTOR_STARTED
- EXECUTOR_EVENT
- EXECUTOR_COMPLETED
- EXECUTOR_FAILED

### Recovery
- RETRY_SCHEDULED(Phase A deterministic 决策;Phase B 起由 RECOVERY_DECIDED 取代)
- VALIDATION_STARTED
- VALIDATION_PASSED
- VALIDATION_FAILED
- FAILURE_CLASSIFIED
- RECOVERY_DECIDED
- RECOVERY_STARTED

### Human Approval Gate(Phase F)
- HUMAN_APPROVAL_REQUIRED
- HUMAN_APPROVAL_GRANTED
- ACTION_SUBMITTED

> 说明:ATTEMPT_FAILED / ATTEMPT_TIMED_OUT / ATTEMPT_CRASHED / ATTEMPT_COMPLETED、
> RUN_* 与 RETRY_SCHEDULED 为 Phase A 实现按"每个状态迁移必须产生 Event"
> 原则补充的扩展,属正式目录的一部分。

## 保留原则
- 正式实验日志不可覆盖
- Secret / Token 不写入日志
- 用户隐私字段需脱敏
- 原始模型输出可保存，但不得成为唯一 Eval 证据

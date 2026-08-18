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
                    ├── context.md
                    ├── executor-events.jsonl
                    ├── stdout.log
                    ├── stderr.log
                    ├── artifacts.json
                    ├── validation.json
                    └── failure.json
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

## V0 Event Type
- TASK_CREATED
- TASK_STARTED
- RUN_CREATED
- RUN_STARTED
- ATTEMPT_STARTED
- CONTEXT_BUILT
- EXECUTOR_STARTED
- EXECUTOR_EVENT
- EXECUTOR_COMPLETED
- EXECUTOR_FAILED
- VALIDATION_STARTED
- VALIDATION_PASSED
- VALIDATION_FAILED
- FAILURE_CLASSIFIED
- RECOVERY_DECIDED
- RECOVERY_STARTED
- HUMAN_APPROVAL_REQUIRED
- HUMAN_APPROVAL_GRANTED
- ACTION_SUBMITTED
- TASK_COMPLETED
- TASK_FAILED
- TASK_ESCALATED

## 保留原则
- 正式实验日志不可覆盖
- Secret / Token 不写入日志
- 用户隐私字段需脱敏
- 原始模型输出可保存，但不得成为唯一 Eval 证据

# Experiment Protocol

## 核心原则
一次实验尽量只改变一个核心变量。

## Experiment Identity
每次正式实验生成唯一 `experiment_id`。

### 格式(以代码实现为准,2026-08-18 定稿)

```text
EXP-YYYYMMDD-<AREA>-<NNN>
```

- `YYYYMMDD`：创建日期(UTC)。
- `<AREA>`：实验领域,如 `RUNTIME`(运行时/恢复)、`JOB`(岗位匹配)、`SWE`(编码)。
- `<NNN>`：该领域内三位序号,从 `001` 递增,只增不覆盖。

示例：

```text
EXP-20260818-RUNTIME-001
EXP-20260818-RUNTIME-002
EXP-20260819-JOB-001
EXP-20260819-JOB-002
```

**设计决策**：详细配置(Harness Version、Context Policy、模型、provider、超时等)
统一记录在 `experiment.json`,不塞进 ID。ID 只负责唯一、可读、可排序;
把变量塞进 ID 会破坏可读性并让 ID 随配置漂移。

## 必须记录
- experiment_id
- timestamp
- git_commit
- branch
- dirty_workspace
- harness_version
- dataset_version
- ground_truth_version
- context_policy_version
- executor
- provider
- model
- reasoning config
- timeout
- max_attempts
- environment

## 版本规则
以下变化必须升级 Harness Version：
- Recovery Policy
- Context Policy
- Validation Policy
- Prompt Template
- Tool Policy
- Orchestration Policy

Benchmark Task / JD / Ground Truth 发生改变：
必须升级 Dataset / Ground Truth Version。

## Baseline
- **B0**：Agent + Task，没有外部 Recovery
- **B1**：Agent + Validator，没有 Recovery
- **H1**：Agent + Validator + Basic Retry
- **H2**：Agent + Validator + Failure-aware Recovery
- **H3**：H2 + Expanded Context Reconstruction

## 第一批实验(示例,按新 ID 格式)

实际已跑实验：
- **EXP-20260818-RUNTIME-001**：Stage 0,CP-0,No Recovery,MockExecutor(HV-0.1)
- **EXP-20260818-RUNTIME-002**：Validation + Failure-aware Recovery,CP-2,MockExecutor(HV-0.2)

规划中的 Job 系列：
- **EXP-YYYYMMDD-JOB-001**：CP-1,Recovery OFF,固定低成本模型,30 JD Baseline
- **EXP-YYYYMMDD-JOB-002**：CP-2,Recovery ON,同上 Dataset

固定模型、Dataset、环境。

## 报告结构
1. Experiment Metadata
2. Hypothesis
3. Configuration
4. Aggregate Results
5. Per-task Results
6. Failure Distribution
7. Recovery Analysis
8. Cost / Efficiency
9. Human Intervention
10. Regression
11. Conclusion
12. Next Experiment

## 实验纪律
禁止：
- 跑完后修改 Acceptance Criteria
- 偷换 Dataset 继续比较
- 失败后人工修核心结果却仍算自动成功
- 同时换模型、Context、Recovery 后宣称某一模块有效

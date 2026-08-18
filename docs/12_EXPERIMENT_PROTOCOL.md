# Experiment Protocol

## 核心原则
一次实验尽量只改变一个核心变量。

## Experiment Identity
每次正式实验生成唯一 `experiment_id`。

建议格式：
`EXP-YYYYMMDD-HVxx-CPxx-MODELxx`

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

## 第一批实验
- **EXP-001**：CP-0，No Recovery
- **EXP-002**：CP-0 + Validator + Basic Retry
- **EXP-003**：CP-1 + Failure-aware Recovery
- **EXP-004**：CP-2 + Expanded Context

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

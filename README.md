# LHAS — Long-Horizon Agent System

LHAS 是一个面向长任务的可验证 Agent Runtime / Harness。通过外部状态管理、
Context 构建、验证、失败分类、Recovery 和 Eval,让现有 Agent 在长任务中更可靠地
完成目标。

完整规范见 `docs/`(00–14,共 15 份文档)。

## 快速开始

```bash
uv sync --extra dev
uv run lhas init-db
uv run lhas stage0          # Phase A Stage 0 实验套件(全部 Mock)
uv run pytest               # 全部测试
```

## 目录结构

```
docs/            项目规范(00–14)+ ADR(docs/adr/)
src/lhas/        LHAS 核心实现
tests/           pytest 测试
tasks/           开发任务 Spec(LHAS-PHASE-A-CORE-01 等)
experiments/     实验记录(EXP-*,只新增不覆盖)
benchmarks/      固定 Benchmark Dataset(如 job-v0.1)
data/            运行数据(SQLite + 日志,gitignored)
```

## 阶段状态

- Phase A — Core Runtime(Task/Run/Attempt/Event + SQLite + MockExecutor + Orchestrator):✅ 完成,EXP-20260818-RUNTIME-001
- Phase B — Validation / Recovery:✅ 完成,EXP-20260818-RUNTIME-002
- Phase C — Job Benchmark:C0(数据集)/ C1(Ground Truth)/ C2(Evaluator)/ C3(AgentExecutor)进行中
- 后续阶段见 `docs/14_ROADMAP.md`

## 实验纪律

- 正式 Eval 只在已 commit 的基线上运行。
- 每个实验记录绑定 `git_commit`;历史实验只新增、不覆盖。

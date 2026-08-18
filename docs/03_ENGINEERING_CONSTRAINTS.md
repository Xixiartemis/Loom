# LHAS 工程约束

## V0 技术栈
- Python 3.11+
- Pydantic
- SQLAlchemy
- SQLite
- pytest
- Typer CLI
- FastAPI 仅预留，V0 后期再接
- React + TypeScript 控制台不属于 V0 必做

## 架构红线
- Core 不允许直接 import Codex 或具体 Provider。
- 所有 Executor 必须实现统一 Protocol。
- 所有外部数据源通过 Provider / Tool Adapter 接入。
- Validator 只判断，不修改任务结果。
- RecoveryPolicy 只决策，不直接执行。
- ContextBuilder 是唯一 Context 组装入口。
- Event 必须来自真实状态变化。
- 不允许把长期 Memory 直接注入 Executor。

## Coding AI 可以做
- 实现明确 Task
- 补充测试
- 修复 Bug
- 生成 boilerplate
- 在当前 Task 范围内小规模重构
- 更新与当前实现直接相关的文档

## Coding AI 禁止做
- 擅自增加 LangGraph、Temporal、Redis、Celery 等框架
- 擅自修改核心领域模型
- 擅自扩大 Task 范围
- 删除测试换取通过
- 降低 Acceptance Criteria
- 吞异常或把失败伪装成成功
- 修改 Benchmark Ground Truth
- 自动增加 Multi-Agent、Vector DB、复杂 Memory
- 顺手重构大量无关代码

## 正式实验约束
正式 Eval 必须记录：
- git commit
- branch
- dirty workspace
- harness version
- dataset version
- context policy version
- executor
- provider
- model
- model config
- environment

正式 Benchmark 默认要求：`dirty_workspace = false`

历史实验目录只新增，不覆盖。

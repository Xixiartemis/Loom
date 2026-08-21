# LHAS 架构设计

## V0 主架构
```text
Goal / TaskSpec
      ↓
Orchestrator
      ↓
ContextBuilder
      ↓
AgentExecutor
      ↓
Validator
      ↓
 ┌───────────────┐
 │               │
PASS             FAIL
 │               │
 ▼               ▼
Complete    FailureClassifier
                  ↓
             RecoveryPolicy
                  ↓
             ContextBuilder
                  ↓
                Retry

全过程：
EventStore → Storage → Eval Runner → Evaluation Report
```

## 核心模块职责
- **Task Layer**：定义要完成什么、约束和验收条件。
- **Orchestrator**：控制 Task / Run / Attempt 状态与流程。
- **ContextBuilder**：决定当前 Attempt 应向 Agent 提供哪些信息。
- **AgentExecutor**：执行任务；Codex、第三方 Agent、Mock 都只是实现。
- **Validator**：独立判断任务是否达到完成标准。
- **FailureClassifier**：将失败映射到统一 Failure Taxonomy。
- **RecoveryPolicy**：根据失败类型和历史结果决定下一步。
- **EventStore**：保存全过程事件。
- **Eval Runner**：在固定 Dataset 上运行实验并汇总指标。

## 关键边界
- Core 不直接依赖 Codex。
- Executor 不修改 Acceptance Criteria。
- Validator 不修代码、不填表单、不重试。
- RecoveryPolicy 不直接访问网页或模型。
- 外部数据必须通过 Provider / Tool Adapter。
- Memory 未来只能通过 ContextBuilder 进入 Executor。
- UI 未来只消费 Event / State，不改变 Runtime 语义。

## 未来扩展接口
```text
AgentExecutor
├─ MockExecutor
├─ GeneralAgentExecutor
├─ CodexExecutor
└─ FutureExecutor

ToolProvider
├─ SearchProvider
├─ BrowserProvider
├─ ResumeProvider
├─ JobSourceProvider
├─ ApplicationProvider
└─ MCPProvider

Workspace
├─ LocalWorkspace
├─ GitWorkspace
├─ DockerWorkspace
└─ RemoteSandbox

Orchestrator
├─ SingleTask
├─ SequentialTask
├─ TaskGraph
└─ DynamicPlanner
```

V0 只实现必要路径，不提前实现未来功能。
## Phase D planning/tool execution

The domain-neutral flow is `Goal → Plan → PlanStep → Capability → Tool → Task → Run → Attempt → Validation → Failure → Recovery`. A linear plan carries `Step Output → Execution Context → Next Step`; approval follows `WAITING → GRANTED → Resume SAME PLAN`.

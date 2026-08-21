# Planner and Tool Foundation (Phase D)

Phase D adds provider-neutral `Goal -> Plan -> PlanStep -> Capability -> Tool` contracts. `DeterministicPlanner` only constructs an allow-listed linear plan; it never executes tools or decides completion. `ToolRegistry` resolves explicit capabilities and rejects unknown names. `PlanExecutionService` persists Goal/Plan/PlanStep, bridges each step to the existing Task/Run/Attempt runtime, and records replayable tool request/result/error/usage payloads in events.

Each completed step persists its output and passes it forward as `Step Output -> Execution Context -> Next Step`. Runtime metadata reads `lhas.HARNESS_VERSION`; this phase does not change that constant. A gated step can resume only after an explicit approval grant.

Capabilities may require human approval. Such steps become `WAITING_FOR_HUMAN_APPROVAL` and no tool call is made. Fake tools are offline test doubles; no web, browser, shell, MCP, real LLM planner, DAG concurrency, or multi-agent behavior is part of this phase.

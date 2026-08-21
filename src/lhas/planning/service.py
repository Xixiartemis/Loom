from typing import Any
from lhas.domain.enums import EventType, ExecutionStatus
from lhas import HARNESS_VERSION
from lhas.domain.models import Task, new_id
from lhas.executors.protocol import ExecutionRequest, ExecutionResult
from lhas.persistence.database import Database
from lhas.persistence.event_store import EventStore
from lhas.persistence.repositories import TaskRepository
from lhas.persistence.planning_repositories import GoalRepository, PlanRepository
from lhas.orchestrator_v2 import RecoveringOrchestrator
from lhas.planning.models import Goal, Plan, PlanStatus, PlanStepStatus
from lhas.planning.planner import Planner
from lhas.tools.registry import ToolRegistry
from lhas.tools.protocol import ToolRequest, ToolResultStatus

class _ToolExecutor:
    name = "ToolRegistryExecutor"
    def __init__(self, registry, step, db, context): self.registry, self.step, self.db, self.context = registry, step, db, context
    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        event = EventStore(self.db)
        try: tool = self.registry.resolve(self.step.capability)
        except KeyError as exc: return ExecutionResult(status=ExecutionStatus.FAILURE, error_type="UNKNOWN_CAPABILITY", error_message=str(exc))
        tr = ToolRequest(tool_call_id=new_id(), task_id=request.task_id, run_id=request.run_id, attempt_id=request.attempt_id,
                         capability=self.step.capability, arguments=self.step.inputs, context={**self.context, **request.context}, metadata=request.metadata)
        event.append(EventType.TOOL_CALL_STARTED, task_id=request.task_id, run_id=request.run_id, attempt_id=request.attempt_id, payload={"request": tr.model_dump(mode="json")})
        try:
            result = await tool.execute(tr)
            typ = EventType.TOOL_CALL_COMPLETED if result.status == ToolResultStatus.SUCCESS else EventType.TOOL_CALL_FAILED
            event.append(typ, task_id=request.task_id, run_id=request.run_id, attempt_id=request.attempt_id, payload={"request": tr.model_dump(mode="json"), "result": result.model_dump(mode="json")})
            status = ExecutionStatus.SUCCESS if result.status == ToolResultStatus.SUCCESS else ExecutionStatus.FAILURE
            import json
            output = result.output if isinstance(result.output, str) else json.dumps(result.output, ensure_ascii=False)
            return ExecutionResult(status=status, output=output, artifacts=result.artifacts, usage=result.usage, raw=result.model_dump(mode="json"), error_type=result.error_type, error_message=result.error_message)
        except Exception as exc:
            event.append(EventType.TOOL_CALL_FAILED, task_id=request.task_id, run_id=request.run_id, attempt_id=request.attempt_id, payload={"request": tr.model_dump(mode="json"), "error": str(exc)})
            return ExecutionResult(status=ExecutionStatus.FAILURE, error_type=type(exc).__name__, error_message=str(exc))
    async def resume(self, request): return await self.execute(request)
    async def cancel(self, run_id): return None
    async def status(self, run_id): return {"run_id": run_id}

class PlanExecutionService:
    def __init__(self, db: Database, planner: Planner, registry: ToolRegistry): self.db, self.planner, self.registry = db, planner, registry
    def _emit(self, typ, payload): EventStore(self.db).append(typ, payload=payload)
    async def execute_goal(self, goal: Goal, *, context: dict[str, Any] | None = None, experiment_id: str | None = None, approved_capabilities: set[str] | None = None, resume_plan_id: str | None = None) -> Plan:
        self._emit(EventType.GOAL_CREATED, {"goal": goal.model_dump(mode="json")})
        GoalRepository(self.db).create(goal)
        plans = PlanRepository(self.db)
        if resume_plan_id:
            plan = plans.get(resume_plan_id)
            if plan is None or plan.goal_id != goal.id: raise KeyError(f"plan not found for goal: {resume_plan_id}")
            self._emit(EventType.HUMAN_APPROVAL_GRANTED, {"plan_id": plan.id, "approved_capabilities": sorted(approved_capabilities or set())})
        else:
            plan = await self.planner.create_plan(goal=goal, capabilities=self.registry.specs(), context=context or {})
            plans.create(plan)
            self._emit(EventType.PLAN_CREATED, {"plan": plan.model_dump(mode="json")})
        if plan.mode.value != "LINEAR":
            raise NotImplementedError(f"unsupported plan mode: {plan.mode.value}")
        self._emit(EventType.PLAN_STARTED, {"plan_id": plan.id})
        task_repo = TaskRepository(self.db)
        execution_context = dict(context or {})
        for step in plan.steps:
            if step.status == PlanStepStatus.COMPLETED:
                execution_context[step.id] = step.output
                execution_context[step.capability] = step.output
                continue
            spec = self.registry.resolve(step.capability).capability
            if step.capability not in (approved_capabilities or set()) and (spec.requires_human_approval or (goal.requires_human_approval and spec.side_effect)):
                step.status = PlanStepStatus.WAITING_FOR_HUMAN_APPROVAL; plan.status = PlanStatus.WAITING_FOR_HUMAN_APPROVAL
                self._emit(EventType.HUMAN_APPROVAL_REQUIRED, {"plan_id": plan.id, "step_id": step.id, "capability": step.capability})
                plans.update(plan); return plan
            step.execution_context = dict(execution_context)
            step.inputs = {**step.inputs, **execution_context}
            task = Task(project_id=goal.project_id, title=step.title, objective=step.objective, constraints=goal.constraints, acceptance_criteria=step.success_criteria, max_attempts=2)
            task_repo.create(task); step.task_id = task.id; step.status = PlanStepStatus.RUNNING
            self._emit(EventType.PLAN_STEP_STARTED, {"plan_id": plan.id, "step_id": step.id, "task_id": task.id})
            orch = RecoveringOrchestrator(self.db, executor_factory=lambda s=step: _ToolExecutor(self.registry, s, self.db, execution_context), executor_type="ToolRegistryExecutor", provider="tool-registry", model="deterministic", harness_version=HARNESS_VERSION, dataset_version="PLANNING-V0.1", experiment_id=experiment_id)
            run = await orch.execute_task(task.id)
            if run.status.value != "COMPLETED":
                step.status = PlanStepStatus.FAILED; plan.status = PlanStatus.FAILED; plans.update(plan); self._emit(EventType.PLAN_STEP_FAILED, {"plan_id": plan.id, "step_id": step.id, "run_id": run.id}); self._emit(EventType.PLAN_FAILED, {"plan_id": plan.id}); return plan
            import json
            payload = json.loads(run.result or "{}")
            step.output = payload.get("output")
            if isinstance(step.output, str):
                try: step.output = json.loads(step.output)
                except json.JSONDecodeError: pass
            execution_context[step.id] = step.output
            execution_context[step.capability] = step.output
            step.status = PlanStepStatus.COMPLETED; plans.update(plan); self._emit(EventType.PLAN_STEP_COMPLETED, {"plan_id": plan.id, "step_id": step.id, "run_id": run.id, "output": step.output})
        plan.status = PlanStatus.COMPLETED; plans.update(plan); self._emit(EventType.PLAN_COMPLETED, {"plan_id": plan.id}); return plan

    async def resume_after_approval(self, plan_id: str, goal: Goal, capability: str, *, context: dict[str, Any] | None = None, experiment_id: str | None = None) -> Plan:
        """Resume by explicitly granting one previously gated capability."""
        return await self.execute_goal(goal, context=context, experiment_id=experiment_id, approved_capabilities={capability}, resume_plan_id=plan_id)

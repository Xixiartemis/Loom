import asyncio
from lhas.domain.models import Project
from lhas.persistence.repositories import ProjectRepository
from lhas.planning.models import Goal, CapabilitySpec, PlanStatus
from lhas.planning.planner import DeterministicPlanner
from lhas.planning.service import PlanExecutionService
from lhas.tools.fakes import FakeTool
from lhas.tools.registry import ToolRegistry

def test_planner_and_tool_execution(db):
    project=Project(name="planning-domain")
    ProjectRepository(db).create(project)
    specs=[CapabilitySpec(name=n,description=n) for n in ("repo.search","repo.read","code.inspect","code.patch","test.run")]
    reg=ToolRegistry()
    for s in specs: reg.register(FakeTool(s))
    goal=Goal(project_id=project.id,objective="propose issue",allowed_capabilities=[s.name for s in specs],metadata={"plan_steps":[s.name for s in specs]})
    plan=asyncio.run(PlanExecutionService(db,DeterministicPlanner(),reg).execute_goal(goal,experiment_id="exp-test"))
    assert plan.status == PlanStatus.COMPLETED
    assert [s.capability for s in plan.steps] == [s.name for s in specs]
    assert all(s.task_id for s in plan.steps)

def test_unknown_capability_rejected():
    goal=Goal(project_id="p",objective="x",allowed_capabilities=["missing"],metadata={"plan_steps":["missing"]})
    try: asyncio.run(DeterministicPlanner().create_plan(goal=goal,capabilities=[],context={}))
    except ValueError as exc: assert "unknown capability" in str(exc)
    else: raise AssertionError("unknown capability must fail explicitly")

def test_human_approval_blocks_execution(db):
    project=Project(name="approval-domain"); ProjectRepository(db).create(project)
    spec=CapabilitySpec(name="code.patch",description="patch",side_effect=True,requires_human_approval=True)
    reg=ToolRegistry(); reg.register(FakeTool(spec))
    goal=Goal(project_id=project.id,objective="patch",allowed_capabilities=[spec.name],metadata={"plan_steps":[spec.name]})
    plan=asyncio.run(PlanExecutionService(db,DeterministicPlanner(),reg).execute_goal(goal))
    assert plan.status == PlanStatus.WAITING_FOR_HUMAN_APPROVAL

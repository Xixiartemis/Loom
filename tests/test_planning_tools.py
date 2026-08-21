import asyncio
from lhas.domain.models import Project
from lhas.persistence.repositories import ProjectRepository
from lhas.planning.models import Goal, CapabilitySpec, PlanStatus
from lhas.planning.planner import DeterministicPlanner
from lhas.planning.service import PlanExecutionService
from lhas.tools.fakes import FakeTool
from lhas.tools.registry import ToolRegistry
from lhas.persistence.planning_repositories import GoalRepository, PlanRepository
from lhas import HARNESS_VERSION
from lhas.persistence.event_store import EventStore
from lhas.domain.enums import EventType
from lhas.persistence.phaseb_repos import FailureReportRepository, RecoveryActionRepository, ValidationResultRepository

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
    resumed=asyncio.run(PlanExecutionService(db,DeterministicPlanner(),reg).resume_after_approval(plan.id,goal,"code.patch"))
    assert resumed.status == PlanStatus.COMPLETED
    assert GoalRepository(db).get(goal.id).objective == goal.objective
    assert PlanRepository(db).get(resumed.id).status == PlanStatus.COMPLETED

def test_inter_step_dataflow_and_harness_version(db):
    project=Project(name="dataflow-domain"); ProjectRepository(db).create(project)
    seen=[]
    def first(req): return {"token":"step-one"}
    def second(req): seen.append(req.arguments); return {"received": req.arguments}
    a=CapabilitySpec(name="a",description="a"); b=CapabilitySpec(name="b",description="b")
    reg=ToolRegistry(); reg.register(FakeTool(a,first)); reg.register(FakeTool(b,second))
    goal=Goal(project_id=project.id,objective="flow",allowed_capabilities=["a","b"],metadata={"plan_steps":["a","b"]})
    plan=asyncio.run(PlanExecutionService(db,DeterministicPlanner(),reg).execute_goal(goal))
    assert plan.status == PlanStatus.COMPLETED and seen and seen[0]["a"] == {"token":"step-one"}
    from lhas.persistence.repositories import RunRepository
    rr=RunRepository(db)
    runs=[rr.list_for_task(s.task_id)[0] for s in plan.steps]
    assert all(r.harness_version == HARNESS_VERSION for r in runs)

def test_tool_failure_enters_recovery_runtime(db):
    project=Project(name="recovery-domain"); ProjectRepository(db).create(project)
    calls=[]
    def scripted(req):
        calls.append(req)
        return "" if len(calls)==1 else {"recovered": True}
    spec=CapabilitySpec(name="recover",description="recover")
    reg=ToolRegistry(); reg.register(FakeTool(spec,scripted))
    goal=Goal(project_id=project.id,objective="recover",allowed_capabilities=["recover"],metadata={"plan_steps":["recover"]})
    plan=asyncio.run(PlanExecutionService(db,DeterministicPlanner(),reg).execute_goal(goal))
    assert plan.status == PlanStatus.COMPLETED and len(calls)==2
    assert len(ValidationResultRepository(db).list_for_attempt(calls[0].attempt_id)) == 1
    assert FailureReportRepository(db).list_for_attempt(calls[0].attempt_id)
    assert RecoveryActionRepository(db).list_for_attempt(calls[0].attempt_id)
    types=[e.event_type for e in EventStore(db).list_all()]
    assert EventType.FAILURE_CLASSIFIED in types and EventType.RECOVERY_STARTED in types

def test_true_approval_resume_same_plan(db):
    project=Project(name="approval-resume"); ProjectRepository(db).create(project)
    counts={n:0 for n in ("one","two","three")}
    def handler(name):
        def run(req): counts[name]+=1; return name
        return run
    reg=ToolRegistry()
    for name,approval in (("one",False),("two",True),("three",False)):
        reg.register(FakeTool(CapabilitySpec(name=name,description=name,side_effect=approval,requires_human_approval=approval),handler(name)))
    goal=Goal(project_id=project.id,objective="approval",allowed_capabilities=["one","two","three"],metadata={"plan_steps":["one","two","three"]})
    svc=PlanExecutionService(db,DeterministicPlanner(),reg)
    waiting=asyncio.run(svc.execute_goal(goal)); assert waiting.status == PlanStatus.WAITING_FOR_HUMAN_APPROVAL and counts == {"one":1,"two":0,"three":0}
    resumed=asyncio.run(svc.resume_after_approval(waiting.id,goal,"two"))
    assert resumed.id == waiting.id and resumed.status == PlanStatus.COMPLETED and counts == {"one":1,"two":1,"three":1}

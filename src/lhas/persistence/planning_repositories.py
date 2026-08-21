from sqlalchemy import select
from lhas.domain.models import json_dumps, json_loads
from lhas.persistence.database import Database
from lhas.persistence.orm import GoalRow, PlanRow, PlanStepRow
from lhas.planning.models import Goal, Plan, PlanStep

class GoalRepository:
    def __init__(self, db): self.db=db
    def create(self, g):
        with self.db.session() as s: s.add(GoalRow(id=g.id,project_id=g.project_id,objective=g.objective,constraints=json_dumps(g.constraints),success_criteria=json_dumps(g.success_criteria),allowed_capabilities=json_dumps(g.allowed_capabilities),requires_human_approval=g.requires_human_approval,metadata_json=json_dumps(g.metadata),created_at=g.created_at))
        return g
    def get(self, i):
        with self.db.session() as s:
            r=s.get(GoalRow,i)
            return Goal(id=r.id,project_id=r.project_id,objective=r.objective,constraints=json_loads(r.constraints) or [],success_criteria=json_loads(r.success_criteria) or [],allowed_capabilities=json_loads(r.allowed_capabilities) or [],requires_human_approval=bool(r.requires_human_approval),metadata=json_loads(r.metadata_json) or [],created_at=r.created_at) if r else None

class PlanRepository:
    def __init__(self, db): self.db=db
    def create(self,p):
        with self.db.session() as s:
            s.add(PlanRow(id=p.id,goal_id=p.goal_id,version=p.version,mode=p.mode.value,status=p.status.value,created_at=p.created_at))
            for i,x in enumerate(p.steps): s.add(PlanStepRow(id=x.id,plan_id=p.id,position=i,title=x.title,objective=x.objective,capability=x.capability,depends_on=json_dumps(x.depends_on),inputs=json_dumps(x.inputs),expected_output=x.expected_output,success_criteria=json_dumps(x.success_criteria),status=x.status.value,task_id=x.task_id))
        return p
    def update(self,p):
        with self.db.session() as s:
            r=s.get(PlanRow,p.id); r.status=p.status.value
            for x in p.steps:
                q=s.get(PlanStepRow,x.id); q.status=x.status.value; q.task_id=x.task_id
        return p

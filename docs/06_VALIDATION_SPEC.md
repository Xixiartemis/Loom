# Validation Spec

## 核心原则
Agent 说“完成”不代表任务完成。

Task Complete 必须由 Validator 根据 Acceptance Criteria 判定。

## 四级 Validation

### V1 Structural Validation
检查数据结构和必填字段。

Job 示例：
- company
- title
- location
- source
- jd_text
- url

### V2 Rule Validation
优先使用确定性规则：
- 毕业年份
- 学历
- 地点
- 是否过期
- 是否重复
- 是否属于目标岗位族
- 是否已经申请

### V3 Semantic Validation
需要模型理解的部分：
- 技能匹配
- 项目匹配
- 职业方向匹配
- 岗位成长价值
- 推荐理由

要求：
- 必须输出 evidence
- 不允许只给分数
- 不允许编造 Resume 或 JD 中不存在的事实

### V4 Action Validation
申请执行前检查：
- 表单字段是否齐全
- 简历附件是否正确
- 姓名/学校/电话等是否一致
- 岗位 ID 是否正确
- 是否重复投递
- 是否达到 READY_TO_SUBMIT

## Submit Gate
V0 强制：
```text
READY_TO_SUBMIT
      ↓
HUMAN_APPROVAL
      ↓
SUBMITTED
```

Executor 不允许绕过该 Gate。

## SWE Benchmark Validation
可使用：
- pytest
- npm test
- typecheck
- lint
- build
- task-specific acceptance test

确定性 Validator 优先于 LLM Judge。

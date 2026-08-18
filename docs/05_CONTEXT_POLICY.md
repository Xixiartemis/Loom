# Context Policy

## 核心原则
Context 不等于完整历史记录。

每个 Attempt 只获得完成当前任务所需的最小、可解释 Context。

所有 Context 必须由 ContextBuilder 生成。

## Context 五层

### C0 Goal
长期目标与当前阶段目标。

### C1 User / Profile
候选人简历、技能、职业目标、地点偏好、已投记录等。

必须版本化：
- resume_version
- candidate_profile_version
- career_goal_version

### C2 Current Task
当前 Task 的 objective、constraints、acceptance criteria。

### C3 External Evidence
JD、公司信息、来源、发布日期、URL 等。

事实尽量附 Source / Evidence。

### C4 Previous Attempts
只提供与当前 Recovery 相关的：
- previous attempt summary
- failure evidence
- missing information
- relevant history
- prior artifacts

禁止直接塞入全部聊天历史。

## V0 Context Policy

### CP-0
`Goal + Current Task`

### CP-1
`CP-0 + Candidate Profile + Necessary Evidence`

### CP-2
`CP-1 + Failure Evidence + Previous Attempt Summary + Relevant History`

## Context Snapshot
每个 Attempt 必须保存完整 Context Snapshot，用于：
- 复盘
- A/B 对比
- Token 分析
- Failure Analysis

## 未来扩展
Memory、RAG、Repo Knowledge、Search History 都只能作为 Context Source，通过 ContextBuilder 统一选择与组装。

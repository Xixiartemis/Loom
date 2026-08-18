# Recovery Policy

## 目标
Recovery 的目标不是无脑重试，而是：

> 根据失败原因增加必要信息或改变执行条件，并判断是否值得继续。

## V0 默认策略

### Attempt 1 失败
`RETRY_WITH_FAILURE_CONTEXT`

增加：
- failure evidence
- validation result
- previous attempt summary

### Attempt 2 失败
`RETRY_WITH_EXPANDED_CONTEXT`

进一步增加：
- relevant history
- missing fields
- related source evidence
- prior artifacts

### Attempt 3 失败
默认：`ESCALATE`

## 特殊 Failure
- **TIMEOUT**：预算允许且安全时 Controlled Retry。
- **NETWORK_ERROR**：先判断外部环境问题，再 Retry。
- **MISSING_CONTEXT**：补充缺失信息后 Retry。
- **STALE_CONTEXT**：重建 Context，不复用旧 Snapshot。
- **CONTEXT_CONFLICT**：Escalate 或请求人工澄清。
- **APPROVAL_REQUIRED**：进入 Human Approval Gate，不算普通 Failure。

## RecoveryAction 至少记录
- action_type
- reason
- new_context_policy
- added_context
- attempt_from
- attempt_to

## 禁止
- 无限 Retry
- 修改 Acceptance Criteria
- 为成功删除失败证据
- 未记录新增 Context 的 Retry
- 对不可逆操作自动重复执行

## 未来扩展
- learned recovery policy
- LLM planner
- tool switching
- model switching
- workspace rollback
- checkpoint recovery

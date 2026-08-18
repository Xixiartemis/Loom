# Failure Taxonomy

## EXECUTION
- TIMEOUT
- EXECUTOR_CRASH
- TOOL_ERROR
- NETWORK_ERROR

## DATA
- EMPTY_RESULT
- INVALID_JD
- DUPLICATE_JOB
- EXPIRED_JOB
- MISSING_REQUIRED_FIELD

## REASONING
- WRONG_MATCH
- WRONG_ASSUMPTION
- BAD_RANKING
- INCOMPLETE_ANALYSIS

## CONTEXT
- MISSING_CONTEXT
- STALE_CONTEXT
- CONTEXT_CONFLICT
- CONTEXT_OVERLOAD

## ACTION
- LOGIN_REQUIRED
- FORM_CHANGED
- FIELD_VALIDATION_ERROR
- UPLOAD_FAILED
- DUPLICATE_APPLICATION
- APPROVAL_REQUIRED

## FALLBACK
- UNKNOWN

## FailureReport 最低要求
每次 Failure 必须回答：
1. 发生了什么？
2. 证据是什么？
3. 属于哪一类 Failure？
4. 下一步需要什么？

示例：
```text
failure_type: MISSING_CONTEXT

evidence:
JD 明确要求硕士，但 Candidate Context 未包含最高学历。

impact:
无法可靠判断硬条件。

suggested_recovery:
补充 education context 后重新执行 Rule Validation。
```

禁止只记录“Agent failed”或“匹配失败”。

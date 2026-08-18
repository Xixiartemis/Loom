# EXP-20260818-RUNTIME-001

git_commit: fcd1305
branch: main
dirty_workspace: False
harness_version: HV-0.1
dataset: RUNTIME-V0.1
context_policy: CP-0
executor: MockExecutor
provider: mock
model: mock-v0
tasks: 5

results:
success-path             PASS
fail-once-pass           PASS
timeout                  PASS
crash                    PASS
three-fail-escalate      PASS

purpose: this record proves the LHAS runtime, state machine,
logging and experiment infrastructure are reliable under MockExecutor.
Each subsequent harness change is compared against this baseline.

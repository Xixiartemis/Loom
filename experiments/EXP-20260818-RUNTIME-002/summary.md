# EXP-20260818-RUNTIME-002

git_commit: 327fb20
branch: main
dirty_workspace: False
harness_version: HV-0.2
dataset: RUNTIME-V0.1
context_policy: CP-2
executor: MockExecutor
provider: mock
model: mock-v0
tasks: 3

results:
recoverable-context      PASS
validation-feedback      PASS
unrecoverable            PASS

purpose: this record proves the LHAS runtime, state machine,
logging and experiment infrastructure are reliable under MockExecutor.
Each subsequent harness change is compared against this baseline.

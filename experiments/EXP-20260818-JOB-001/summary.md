# EXP-20260818-JOB-001

git_commit: be762af
branch: main
dirty_workspace: False
dataset: JOB-V0.1
ground_truth_status: {'DRAFT': 30}
predictor: rule
model: -
harness_version: HV-0.2
context_policy: CP-1
recovery: OFF

metrics:
  hard_constraint_accuracy     1.000
  fit_classification_accuracy  1.000
  precision@5                  1.000
  recall@10                    0.500
  ranking_quality(ndcg@10)     1.000
  evidence_accuracy            0.806
  hallucination_rate           0.000
  duplicate_detection_rate     1.000
  expired_job_detection_rate   1.000

n_jobs: 30

purpose: baseline B0 — deterministic rule predictor, no model involved.

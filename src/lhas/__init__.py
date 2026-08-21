"""LHAS (Long-Horizon Agent System) — verifiable agent runtime / harness."""

__version__ = "0.1.0"

# Harness version: bump whenever Recovery / Context / Validation / Orchestration
# policy changes (docs/12_EXPERIMENT_PROTOCOL.md). Phase B added the
# Hardening modified Prompt Template / Validation / Recovery Context wiring;
# Phase D changed planner/tool orchestration semantics -> HV-0.4.
HARNESS_VERSION = "HV-0.4"

# Default dataset / context-policy labels used by experiment records.
DEFAULT_DATASET_VERSION = "RUNTIME-V0.1"
DEFAULT_CONTEXT_POLICY_VERSION = "CP-0"
DEFAULT_PROVIDER = "mock"
DEFAULT_MODEL = "mock-v0"

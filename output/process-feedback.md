# Process Feedback — rebuilder-evergreen-tvevents

**Date**: 2025-07-13

## Manual Corrections Received

### 1. "Start over at Ideation — docs before code"

**Instruction:** The operator directed the agent to delete all existing code and
restart at Phase 1 Step 1 because code was being generated before Phase 1
documentation was complete.

**Why the process didn't handle it:** The IDEATION_PROCESS.md is clear that
Phase 1 must complete before Phase 2. The agent violated this by jumping ahead.
The process document itself was correct; the agent execution was at fault.

**Proposed fix:** Add a gate check annotation to the process:
> **HARD GATE**: Phase 2 (Step 12) MUST NOT begin until Steps 1–11a are all
> marked complete. If any Phase 1 artifact is missing, stop and produce it.

### 2. "Do not use tv-collection-services or vizio-automate as references"

**Instruction:** The operator specified that the other rebuild-inputs directories
should not be used as reference material — this rebuild must be standalone.

**Why the process didn't handle it:** The IDEATION_PROCESS.md does not address
cross-contamination between rebuild-inputs directories. When multiple rebuilds
coexist in the workspace, the agent may incorrectly infer patterns from adjacent
work.

**Proposed fix:** Add to IDEATION_PROCESS.md:
> When multiple `rebuild-inputs/` directories exist, treat each as a fully
> independent project. Do not reference or copy patterns from other rebuild
> directories unless the `input.md` scope explicitly lists them as adjacent
> dependencies.

## Docker Build Failure

During Step 13b (Docker Runtime Validation), the initial `docker build` failed
because the Dockerfile copied `pyproject.toml` before `src/` but the setuptools
config (`[tool.setuptools.packages.find] where = ["src"]`) required `src/` to
exist at install time. This was fixed by reordering `COPY` instructions.

**Proposed fix:** Add to Step 13b common failures table:
> | `error in 'egg_base' option: 'src' does not exist` | Dockerfile copies
> `pyproject.toml` before `src/` when `setuptools.packages.find` needs `src/`
> present at wheel build time | Move `COPY src/ ./src/` before `RUN pip install .` |

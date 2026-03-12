# Project Instructions — Auto-loaded by GitHub Copilot in VS Code
#
# This file ensures the developer agent prompt and project config are read
# before any coding work begins. VS Code with GitHub Copilot reads
# `.github/copilot-instructions.md` automatically and includes it in every
# Copilot Chat interaction.

## Required Context

Before writing any code, making any changes, or answering any questions about
this project, you MUST read these two files in full:

1. `developer-agent/skill.md` — development standards, coding practices,
   testing expectations, CI/CD pipeline structure, service bootstrap checklist,
   and observability requirements.
2. `developer-agent/config.md` — project-specific configuration: commands,
   environments, services, secrets references, and SRE agent integration.

Do not proceed with any task until both files have been read. These files define
the standards every change must conform to.

## Session Greeting

At the start of every new conversation, after reading both files, confirm by
stating: **"Loaded evergreen-tvevents developer standards from skill.md and
config.md."** If you cannot find or read either file, say so
explicitly instead of proceeding silently.

## Quick Reference

- Run tests: `pytest tests/ --cov=src/app --cov-fail-under=80`
- Run locally: `uvicorn src.app.main:app --reload`
- Lint: `ruff check src/ tests/ && ruff format --check src/ tests/`
- Type check: `mypy src/app/`
- Service bootstrap checklist: skill.md → Service Bootstrap section
- Observability contract: skill.md → Observability section
- CI/CD pipeline: skill.md → CI/CD section + config.md CI/CD section

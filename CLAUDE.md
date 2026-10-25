# FPL Analytics: agent instructions

Read `docs/wiki/README.md` first. It indexes the project wiki (status, architecture, data gotchas,
decisions, task log). **Every task must update the wiki before it finishes** (see "Maintaining the
wiki" in that README) so the next session can pick up the work.

## Conventions
- User is an experienced Python engineer; skip beginner explanations. Windows / PowerShell, venv at `.venv`.
- Python 3.11+, ruff (check only in CI), pytest. Tests must not hit live APIs (`httpx.MockTransport`,
  in-memory DuckDB). Add dependencies to `pyproject.toml` optional extras only when needed.
- Short-lived branches + PRs; the ruleset requires checks `test (3.11)` / `test (3.13)`.
  Do not commit or push unless asked. `gh` is at `C:\Program Files\GitHub CLI\gh.exe`.
- Do not add "Co-Authored-By" or "Generated with Claude Code" lines to commit messages or PR bodies.
- Never commit the FPL entry id (user env var `FPL_ENTRY_ID`) or anything under `data/`.

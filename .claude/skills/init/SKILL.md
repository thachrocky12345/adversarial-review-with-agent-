# /init — Full Project Sync Skill

When `/init` is invoked, follow **every** step below in order. Do not skip any step even if nothing appears to have changed.

---

## 1. Scan the Full Project Structure

- Recursively scan the entire project directory.
- Identify all source files, configuration files, dependency manifests (`requirements.txt`, `pyproject.toml`), and infrastructure files.
- Note any new, removed, or renamed files since the last run.

## 2. Update CLAUDE.md

Refresh the following sections in `CLAUDE.md` (create them if missing, preserve all other content):

- **Tech Stack** — detect from `pyproject.toml`, `requirements.txt`, or import statements.
- **Project Structure** — regenerate from the current directory tree (exclude `.git`, `__pycache__`, `venv`, `.venv`, `*.pyc`, `.idea`, `node_modules`).
- **Key Modules** — detect from `src/` or the main package directory; list each module with a one-line description.
- **Known Dependencies** — list every direct dependency with its pinned or minimum version. Update the `Last synced` date to today.

## 3. Update docs/architecture.md

- Set **Last Updated** to today's date.
- Refresh **Tech Stack**, **System Layers**, and **Key Modules** to reflect the current project state.
- Add any newly detected layers or dependencies.
- Link any new ADRs in the **Recent Decisions** section.

## 4. Process docs/decisions/.pending_adr_review

If the file `docs/decisions/.pending_adr_review` exists:

### CREATE a new ADR when you detect:
- A new major framework (e.g., FastAPI, Django, Flask)
- A new database driver (e.g., psycopg2, SQLAlchemy, motor)
- A new auth library (e.g., PyJWT, python-jose, authlib)
- A new infrastructure file (e.g., Dockerfile, docker-compose.yml, terraform/)

### DEPRECATE an existing ADR when:
- A library listed in an accepted ADR has been removed from the dependency manifest.

### UPDATE ADR status when:
- A library has been superseded by another (mark old ADR as `Superseded by ADR-XXXX`).

### SKIP (do not create ADRs for):
- Minor version bumps of already-tracked dependencies.
- Dev/test-only dependencies: `pytest`, `black`, `ruff`, `mypy`, `isort`, `flake8`, `pre-commit`, `coverage`, `tox`.

Use the template at `docs/decisions/_template.md` for new ADRs. Number them sequentially based on the highest existing ADR number.

## 5. Update docs/decisions/index.md

After any ADR creation, deprecation, or status change, regenerate the table in `docs/decisions/index.md` to reflect all current ADRs.

## 6. Clean Up

- Delete `docs/decisions/.pending_adr_review` after processing (or after confirming nothing to process).

## 7. Update Known Dependencies Baseline

- Overwrite the **Known Dependencies** section in `CLAUDE.md` with the current full dependency list.
- Update the `Last synced` timestamp.

## 8. Output Summary

Print a summary in this exact format:

```
✅ Init sync complete — updated: [comma-separated list of files modified], created ADRs: [list or "none"], skipped: [reasons or "none"]
```
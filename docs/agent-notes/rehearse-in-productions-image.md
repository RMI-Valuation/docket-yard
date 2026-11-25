---
name: rehearse-in-productions-image
description: "Run a migration's tests and rehearsal inside production's image (its SQLite), not on this workstation's newer engine"
metadata:
  type: feedback
---

Rehearse and test any migration INSIDE production's own image (`ghcr.io/rmi-valuation/docket-yard:<live tag>`, SQLite 3.46.1 on Debian 13 as of 2026-09-13), with the branch mounted and first on `PYTHONPATH`. A production COPY on this workstation is not enough.

**Why:** on 2026-09-13, migration 0029 passed 854 local tests and two full rehearsals on a production restore, then failed CI with 485 failures and 163 errors. Its abort message joined two literals with `||`, and `RAISE` only accepts an expression from SQLite 3.47.0. The workstation runs 3.50.4; CI (Ubuntu 24.04) and production (3.46.1) don't. I had even tested that exact `RAISE` limit in the image the same day, then rehearsed the real migration on the newer engine. Production's deploy would have failed at `migrate` behind the wall.

**CI'S PYTHON ENVIRONMENT IS ALSO NARROWER THAN THIS BOX'S.** On 2026-09-18 a new test in
`tests/test_fleet.py` loaded `tools/fleet/dots_worker.py` for two of its constants and went red
on main twice: that module imports `fitz` (pymupdf) AT THE TOP on purpose — "so a venv without
it fails here, not per page" — and CI installs no pymupdf. `hunyuan_worker.py` imports it
lazily, which is why the tabular tests never hit it. A test that loads a fleet worker module
must stub `fitz` in `sys.modules` first. To prove such a fix without CI, run pytest behind a
meta-path finder that raises `ModuleNotFoundError` for the module in question, rather than
trusting a machine that has it.

**How to apply:**
- Mount the repo at `/src`, run as `--user root`, set `PYTHONPATH=/src/src`, and print `sqlite3.sqlite_version` plus `docketyard.__file__` first, to prove the engine and the code.
- Run tests from a mounted script piped through `tr -d '\r'`. PowerShell mangles nested quotes in `sh -c`.
- Use `--basetemp=/tmp/...` so root-owned files don't land in the repo.
- Engine drift is recorded in `docs/deferred.md` § SQLite 3.53.4. See [[claims-are-not-measurements]] and [[state-the-question-before-measuring]].

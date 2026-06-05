# Project Status

**Version `0.5.0`** — a portfolio **workbench MVP**, not a released product. The
`0.x` line is deliberate: the reachable product is real and tested, but the
project is single-machine / single-user and carries a stratum of unreachable
research code from an earlier era (see *Honest scope* below).

> This file is a short, version-stamped headline. The **authoritative** honest
> breakdown of "what is real vs not" lives in the README's
> [范围与状态](README.md#范围与状态) section and `docs/ASSESSMENT-2026-05-29.md`
> — this file defers to those rather than duplicating them.

## What actually runs (reachable product path)

- **Engine** — numpy-only 2D plane-stress / 2.5D SIMP compliance minimization
  (optimality-criteria updates), with **independent re-solve verification**
  (`verify_run` never raises: an engineering negative like `connectivity_failed`
  is a legitimate recorded outcome, not a crash). Source: `structure_optimizer/core/`.
- **CLI** — `structure-optimizer` with subcommands `run / verify / report /
  demo / export / study` (`structure_optimizer/cli.py`). Each run writes a
  self-contained record (`summary.json`, `verification.json`, `density.npy`,
  `metrics.csv`, PNGs, a convergence GIF, `report.md`).
- **Benchmarks** — 18 configs auto-discovered from
  `structure_optimizer/benchmarks/configs/*.json` (`registry.available_benchmarks`).
- **Web workbench (M1–M4)** — FastAPI backend runs the synchronous engine on a
  worker thread and streams per-iteration frames over a WebSocket; React + Vite
  frontend (pick → edit config → live convergence → verification → export
  SVG/DXF/STL / compare runs). Single-user, one in-flight run. Source: `server/`, `web/`.
- **Deterministic pipeline agent-rail** — the run is organized as ordered
  **non-LLM** stages, each with an explicit precondition / gate / postcondition;
  gates fail-closed. The trace records 7 stages (`problem_definition → mesh →
  optimizer → convergence_gate → persistence → verification → export_report`);
  the user-facing "六小匠" narrative counts the 6 engineering stages
  (`persistence` is the internal run-store step). Every run writes
  `agents_trace.json`, so the web "讲解模式" renders the **real executed stages**,
  not a scripted narrative. "agent" here = a contract-bearing pipeline stage
  with no intelligence / autonomy / AI. Source: `structure_optimizer/core/pipeline.py`.

## Honest scope (permanent red lines)

- 2D plane-stress / 2.5D only — **no 3D**.
- **No LLM / AI advisor** — out of scope.
- Single-machine, single-user; in-memory store of the most recent runs.
- `structure_optimizer/core/` also contains ~30 experimental v6–v16 "wave"
  research modules that are **unreachable from the CLI / workflow / benchmarks**
  and are NOT product features. Full candid account: `docs/ASSESSMENT-2026-05-29.md`.
  The `[5.0.0]` line in `CHANGELOG.md` and the `v5.0` design-doc headings are
  historical archive, not the current capability set.

## Version note

`0.5.0` resolves a prior inconsistency where `pyproject.toml` advertised
`5.0.0` (a leftover tag from the abandoned "self-grading treadmill" era flagged
in `docs/ASSESSMENT-2026-05-29.md`) while the package self-reported `0.1.0`. The
single honest source of truth is now `0.5.0` across `pyproject.toml`,
`structure_optimizer/__init__.py`, and the FastAPI app.

## Verify

```
python -m pytest                 # engine + server test suite
structure-optimizer --version    # -> structure-optimizer 0.5.0  (after an editable reinstall)
cd web && npm run build          # tsc --noEmit + Vite production build
```

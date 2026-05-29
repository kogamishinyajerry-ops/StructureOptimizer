# Project Overview

An honest map of this repository for a reader landing here cold (e.g. a hiring
reviewer). It distinguishes what is **live and reachable** from what is
**exploratory research code that is not wired in**. For the full retrospective,
read [`docs/ASSESSMENT-2026-05-29.md`](ASSESSMENT-2026-05-29.md).

StructureOptimizer is a local, dependency-light 2D/2.5D SIMP topology-optimization
tool, now fronted by a web workbench. It is being finalized as a **portfolio
piece** — judged on showcase quality and honesty — not shipped as a product.

---

## 1. The live engine

`structure_optimizer/` implements SIMP (Solid Isotropic Material with
Penalization) compliance minimization via the optimality-criteria update. The
engine core is **numpy-only** (no heavy solver dependencies).

### CLI

The package installs a console entry point (`structure-optimizer`, see
`[project.scripts]` in `pyproject.toml`). The parser is built in
`structure_optimizer/cli.py` (`build_parser()`, argparse) and registers **six
subcommands**:

- `run` — run a benchmark SIMP optimization
- `verify` — independently re-check / validate a completed run
- `report` — produce the run report
- `demo` — run a packaged demonstration
- `export` — export geometry from a run
- `study` — run a parameter study

### Run store

Each run persists a self-contained artifact set:

- `input.json` — the resolved problem definition
- `density.npy` — the final density field
- `metrics.csv` — per-iteration metrics
- `summary.json` — run summary
- `verification.json` — verification results
- `manufacturability.json` — manufacturability checks
- `report.md` — human-readable report
- plus rendered `PNG`s and a `gif`

---

## 2. The web workbench

Branch `feat/web-workbench-m1`, PR #1 (open to `main`). The single engine change
required for the workbench is an **optional, default-off `on_iteration` callback**
on `run_simp`: with the default (`None`) the CLI/test path is byte-identical, so
reproducibility is unaffected.

### Backend — `server/` (FastAPI)

Optional `[web]` extra pulls in fastapi + uvicorn. The streaming model:

- a **worker thread** runs the synchronous engine;
- the `on_iteration` callback pushes per-iteration frames onto a thread-safe
  `queue.Queue`;
- an **async task** drains that queue to a **WebSocket** client;
- `RunManager` keeps the last **16** runs in memory.

Endpoints:

- `GET  /api/benchmarks` — list benchmarks
- `GET  /api/benchmarks/{id}/config` — benchmark config
- `POST /api/runs` — start a run
- `GET  /api/runs` — run history
- `GET  /api/runs/{id}` — run detail + metrics
- `WS   /api/runs/{id}/stream` — live per-iteration stream
- `GET  /api/runs/{id}/export` — geometry export (`svg` / `dxf` / `stl`)
- `GET  /api/health` — health check

### Frontend — `web/` (React 18 + TypeScript strict + Vite)

- A CSS **design-token system** (`web/src/theme/tokens.css`) is the single source
  of truth — tokens only.
- **No chart library**: the convergence chart is a hand-rolled SVG; the density
  viewport is a canvas.

### Shipped milestones

- **M1** — live convergence viewport
- **M2** — SVG / DXF / STL geometry export
- **M3** — problem-definition editor; caps enforced **server-side** (HTTP 400),
  mirrored client-side to block Run before submit
- **M4** — run history + reopen
- **Export disclaimer / provenance** — SVG XML comment + DXF 999 group codes
- **Comparison** — side-by-side two-run comparison (frontend-only modal)

---

## 3. What's exploratory / not wired in

Be clear-eyed about this: `structure_optimizer/core/` contains roughly 54 modules,
and about **30 of them are the v6–v16 "waves"** — higher-smoothness
Korobov/CBC quasi-Monte-Carlo, copula reliability, KKT shadow-price, and similar.
These are **unreachable from the CLI, the workbench, and the benchmarks** (zero
references). They are **exploratory / experimental research code**, not product
features, and should not be read as such.

This history is documented honestly as debt in
[`docs/ASSESSMENT-2026-05-29.md`](ASSESSMENT-2026-05-29.md). The `docs/` directory
also contains numerous historical `blueprint-vN` / `quality-rubric-vN` files from
that period; they are kept for the record but are not the story of the project.

---

## 4. How to evaluate this repo

1. **Run the workbench** — start the FastAPI backend (`server/`) with the `[web]`
   extra and the Vite frontend (`web/`); start a run and watch the live
   convergence viewport stream.
2. **Read the streaming seam** — `server/runner.py` is the heart of the design:
   the synchronous engine on a worker thread, the `on_iteration` → `queue.Queue`
   → WebSocket hand-off.
3. **Read the honest retrospective** — [`docs/ASSESSMENT-2026-05-29.md`](ASSESSMENT-2026-05-29.md)
   for what is real, what is dead, and why.

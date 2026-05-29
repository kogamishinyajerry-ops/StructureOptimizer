# StructureOptimizer Workbench (Milestone 1)

An experience-grade web workbench over the StructureOptimizer numpy engine. Milestone 1 = the
**live convergence viewport**: pick a benchmark → Run → watch the topology emerge in real time →
read the verification result.

- **Backend**: FastAPI (`server/`), wraps the engine, streams per-iteration frames over WebSocket.
- **Frontend**: React + TypeScript + Vite (`web/`), modern-SaaS-minimal UI, canvas density viewport.

## Run it

Two terminals from the repo root.

**1. Backend** (needs the `[web]` extra — fastapi + uvicorn):

```bash
# one-time, into the project venv (uses uv):
VIRTUAL_ENV=.venv uv pip install fastapi "uvicorn[standard]"
# start the API on :8000
.venv/bin/python -m uvicorn server.app:app --reload --port 8000
```

**2. Frontend** (Vite dev server on :5173, proxies `/api` → :8000):

```bash
cd web
npm install      # one-time
npm run dev
```

Open http://localhost:5173 — select a benchmark, hit **Run optimization**, watch it converge.

## Verify without a browser

```bash
.venv/bin/python -m server._smoke      # in-process REST + WebSocket end-to-end check
cd web && npm run build                # tsc --noEmit + vite production build
```

## What's wired

- `GET /api/benchmarks` — runnable benchmarks (recommended first; large meshes excluded).
- `POST /api/runs {benchmark_id, preset?}` — starts a run in a worker thread.
- `WS /api/runs/{id}/stream` — `iteration` frames (density + metrics) → `done` (summary + verification).
- `GET /api/runs/{id}` — final summary + verification + density.

The only engine change is an optional `on_iteration` callback in `core/simp.py` (default-off, CLI
path unchanged). Density frames mirror the engine's PNG colormap and orientation so the live view
matches the saved `density.png`.

## Not yet (future milestones)

Custom problem definition (loads/BCs/mesh editor), geometry export buttons (SVG/DXF/STL), study /
Pareto UI, run history. Reliability is "good enough" for a single local user, single in-flight run.

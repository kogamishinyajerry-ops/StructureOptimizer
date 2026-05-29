# StructureOptimizer Web Workbench

An experience-grade web front end for the SIMP topology-optimization engine:
define a problem, watch it converge live, browse past runs, and export the
result geometry — all driving the same numpy-only engine the CLI uses.

## Shipped

- **M1 — live convergence viewport.** A canvas density viewport plus a
  hand-rolled SVG convergence chart, both fed by per-iteration frames streamed
  over a WebSocket while the engine runs.
- **M2 — geometry export.** Export the final design as SVG, DXF, or STL.
- **M3 — problem-definition editor.** Edit the run config in the browser; the
  server enforces caps (rejecting over-cap configs with HTTP 400), and the
  client mirrors those caps to block an invalid Run before it is sent.
- **M4 — run history + reopen.** Past runs are listed and can be reopened to
  inspect their metrics and final density.
- **Export disclaimer / provenance.** Exports carry a provenance/disclaimer
  note inline — an XML comment in SVG and `999` group codes in DXF.
- **Two-run comparison.** A frontend-only modal places two runs side by side.

## Layout

- `server/` — FastAPI backend. Runs the synchronous engine on a worker thread;
  an `on_iteration` callback pushes per-iteration frames onto a thread-safe
  queue, and an async task drains the queue to a WebSocket. A `RunManager`
  keeps the last 16 runs in memory.
- `web/` — React 18 + TypeScript (strict) + Vite frontend. The CSS design-token
  system in `web/src/theme/tokens.css` is the single source of truth for
  styling — tokens only, no chart library (the convergence chart is hand-rolled
  SVG), canvas density viewport.

## Backend

Needs the `[web]` extra (fastapi + uvicorn). From the repo root:

```bash
# one-time, into the project venv (uses uv):
VIRTUAL_ENV=.venv uv pip install -e ".[web]"
# start the API on :8000
.venv/bin/python -m uvicorn server.app:app --reload --port 8000
```

The server exposes:

- `GET /api/benchmarks` — list bundled benchmark problems.
- `GET /api/benchmarks/{id}/config` — default config for a benchmark.
- `POST /api/runs` — start a run (body: full run config; over-cap → HTTP 400).
- `GET /api/runs` — run history (most recent first).
- `GET /api/runs/{id}` — run detail + metrics.
- `WS /api/runs/{id}/stream` — live per-iteration frames.
- `GET /api/runs/{id}/export` — export final geometry (svg / dxf / stl).
- `GET /api/health` — liveness probe.

## Frontend

```bash
cd web
npm install
npm run dev
```

The dev server runs on :5173 and proxies `/api` to the backend on :8000.

## Verify without a browser

```bash
.venv/bin/python -m server._smoke      # in-process REST + WebSocket end-to-end check
cd web && npm run build                # tsc --noEmit + vite production build
```

The smoke script exercises the REST + WebSocket path end-to-end in-process — no
browser required.

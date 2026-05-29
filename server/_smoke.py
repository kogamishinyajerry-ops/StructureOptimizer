"""In-process smoke test of the workbench API (REST + WebSocket).

Run: .venv/bin/python -m server._smoke
Exercises GET /api/benchmarks, POST /api/runs, WS stream, GET /api/runs/{id}.
"""

from __future__ import annotations

import base64

import numpy as np
from fastapi.testclient import TestClient

from server.app import app


def main() -> int:
    client = TestClient(app)

    benches = client.get("/api/benchmarks").json()
    print(f"benchmarks: {len(benches)} (first={benches[0]['id']}, recommended={benches[0]['recommended']})")
    assert any(b["id"] == "mbb_beam" for b in benches), "mbb_beam missing"
    assert all(b["id"] not in {"large_cantilever", "xlarge_cantilever"} for b in benches), "excluded leaked"

    start = client.post("/api/runs", json={"benchmark_id": "mbb_beam", "preset": "smoke"}).json()
    run_id = start["run_id"]
    nelx, nely = start["nelx"], start["nely"]
    print(f"started run {run_id}  dims={nelx}x{nely}")

    iters = 0
    last_compliance = None
    done = None
    with client.websocket_connect(f"/api/runs/{run_id}/stream") as ws:
        while True:
            frame = ws.receive_json()
            if frame["type"] == "iteration":
                iters += 1
                last_compliance = frame["compliance"]
                exp = nely * nelx
                raw = base64.b64decode(frame["density_b64"])
                assert len(raw) == exp, f"density bytes {len(raw)} != {exp}"
                assert frame["shape"] == [nely, nelx], frame["shape"]
            elif frame["type"] == "done":
                done = frame
                break
            elif frame["type"] == "error":
                print("ERROR frame:", frame["message"])
                return 1

    assert done is not None, "no done frame"
    assert iters >= 1, "no iteration frames"
    print(f"streamed {iters} iteration frames; final compliance={last_compliance:.3f}")
    print(
        f"done: stop_reason={done['stop_reason']} iterations={done['iterations']} "
        f"verif_status={done['verification'].get('status')}"
    )

    result = client.get(f"/api/runs/{run_id}").json()
    ws_final = np.frombuffer(base64.b64decode(done["density_b64"]), dtype=np.uint8)
    api_final = np.frombuffer(base64.b64decode(result["density_b64"]), dtype=np.uint8)
    assert np.array_equal(ws_final, api_final), "WS done density != GET density"
    print(f"GET /api/runs/{run_id}: status={result['status']} density-cross-check=OK")
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

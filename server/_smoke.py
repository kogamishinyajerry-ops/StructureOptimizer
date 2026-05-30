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

    # Geometry export — all three formats download non-empty attachments.
    # (svg/dxf carry a prepended provenance comment, so the format sentinel is no
    # longer at byte 0 — check the whole body.)
    for fmt, sentinel in (("svg", b"<svg"), ("dxf", b"SECTION"), ("stl", b"solid")):
        resp = client.get(f"/api/runs/{run_id}/export", params={"format": fmt})
        assert resp.status_code == 200, f"{fmt} export -> {resp.status_code}"
        body = resp.content
        assert len(body) > 0, f"{fmt} export empty"
        assert sentinel in body, f"{fmt} export missing {sentinel!r}"
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd and f".{fmt}" in cd, f"{fmt} bad disposition: {cd}"
        print(f"export {fmt}: {len(body)} bytes, {cd}")

    # Provenance/disclaimer header is embedded in the text formats (svg comment,
    # dxf 999 group codes); STL carries provenance via the filename only.
    svg_body = client.get(f"/api/runs/{run_id}/export", params={"format": "svg"}).content
    dxf_body = client.get(f"/api/runs/{run_id}/export", params={"format": "dxf"}).content
    assert b"NOT a certified result" in svg_body, "svg missing disclaimer"
    assert b"<!--" in svg_body and b"input_hash" in svg_body, "svg missing provenance comment"
    assert b"NOT a certified result" in dxf_body, "dxf missing disclaimer"
    assert b"999" in dxf_body, "dxf missing 999 comment group code"
    print("export provenance: svg+dxf carry disclaimer + input_hash")

    bad = client.get(f"/api/runs/{run_id}/export", params={"format": "obj"})
    assert bad.status_code == 400, f"bad format should 400, got {bad.status_code}"

    # ---- Milestone 3: problem-definition editor (config + override path) -----
    cfg = client.get("/api/benchmarks/cantilever/config")
    assert cfg.status_code == 200, f"config -> {cfg.status_code}"
    cfg_body = cfg.json()
    for key in ("benchmark_id", "optimization", "mesh", "loads", "loads_editable", "selectors", "limits"):
        assert key in cfg_body, f"config missing '{key}'"
    assert cfg_body["benchmark_id"] == "cantilever"
    assert cfg_body["loads_editable"] is True, "cantilever should be loads_editable"
    assert len(cfg_body["selectors"]) == 13, f"expected 13 selectors, got {len(cfg_body['selectors'])}"
    assert cfg_body["limits"] == {
        "nelx_max": 160,
        "nely_max": 160,
        "elements_max": 12000,
        "max_iterations_max": 200,
    }, cfg_body["limits"]
    print(
        f"config cantilever: opt.vf={cfg_body['optimization']['volume_fraction']} "
        f"mesh={cfg_body['mesh']['nelx']}x{cfg_body['mesh']['nely']} loads={len(cfg_body['loads'])}"
    )

    over = {
        "benchmark_id": "cantilever",
        "overrides": {
            "optimization": {
                "volume_fraction": 0.3,
                "penalty": 3.0,
                "filter_radius": 1.5,
                "max_iterations": 12,
            },
            "mesh": {"nelx": 40, "nely": 20},
        },
    }
    ostart = client.post("/api/runs", json=over)
    assert ostart.status_code == 200, f"override run -> {ostart.status_code}: {ostart.text}"
    ostart_body = ostart.json()
    assert ostart_body["nelx"] == 40 and ostart_body["nely"] == 20, (
        f"override dims {ostart_body['nelx']}x{ostart_body['nely']} != 40x20"
    )
    orun_id = ostart_body["run_id"]
    print(f"override run {orun_id} dims={ostart_body['nelx']}x{ostart_body['nely']}")

    odone = None
    with client.websocket_connect(f"/api/runs/{orun_id}/stream") as ws:
        while True:
            frame = ws.receive_json()
            if frame["type"] == "iteration":
                assert frame["shape"] == [20, 40], frame["shape"]
            elif frame["type"] == "done":
                odone = frame
                break
            elif frame["type"] == "error":
                print("ERROR frame (override run):", frame["message"])
                return 1
    assert odone is not None, "override run no done frame"
    print(f"override run streamed to done: stop_reason={odone['stop_reason']}")

    bad_vf = client.post(
        "/api/runs",
        json={
            "benchmark_id": "cantilever",
            "overrides": {
                "optimization": {"volume_fraction": 1.5, "penalty": 3.0, "filter_radius": 1.5, "max_iterations": 12}
            },
        },
    )
    assert bad_vf.status_code == 400, f"invalid volume_fraction should 400, got {bad_vf.status_code}"
    print(f"invalid volume_fraction -> 400: {bad_vf.json()['detail']}")

    over_cap = client.post(
        "/api/runs",
        json={"benchmark_id": "cantilever", "overrides": {"mesh": {"nelx": 9999, "nely": 20}}},
    )
    assert over_cap.status_code == 400, f"over-cap mesh should 400, got {over_cap.status_code}"
    print(f"over-cap mesh -> 400: {over_cap.json()['detail']}")

    # ---- Milestone 4: run history (list + reopen with metrics) ---------------
    runs_resp = client.get("/api/runs")
    assert runs_resp.status_code == 200, f"list runs -> {runs_resp.status_code}"
    runs = runs_resp.json()
    assert isinstance(runs, list), f"runs not a list: {type(runs)}"
    mbb = next((r for r in runs if r["run_id"] == run_id), None)
    assert mbb is not None, f"mbb_beam run {run_id} missing from history"
    assert mbb["status"] == "done", f"mbb_beam status={mbb['status']}"
    assert isinstance(mbb["compliance"], (int, float)), f"compliance not numeric: {mbb['compliance']!r}"
    assert isinstance(mbb["verified"], bool), f"verified not bool: {mbb['verified']!r}"

    detail = client.get(f"/api/runs/{run_id}").json()
    metrics = detail["metrics"]
    assert isinstance(metrics, list) and metrics, "metrics list empty"
    for key in ("iteration", "compliance", "volume_fraction"):
        assert key in metrics[0], f"metric row missing '{key}'"
    print(
        f"M4 history: {len(runs)} runs; mbb_beam compliance={mbb['compliance']:.3f} "
        f"verified={mbb['verified']} metrics={len(metrics)} rows"
    )

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

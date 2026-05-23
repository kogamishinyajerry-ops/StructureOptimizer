# v5 Quality Rubric (100 pts · ≥ 99 to ship)

> v5 charter: multi-physics 2D topology optimization within numpy-only +
> no-GUI + no-cloud + no-3D + no-commercial-solvers permanent red lines.
> `python scripts/test_agent.py` enforces this rubric mechanically.

## §1 Multi-physics algorithms (30 pts)

| Code | Item | Pts | Mechanism |
|------|------|-----|-----------|
| 1.1  | 热传导 TO（thermal SIMP） | 6 | `core/thermal_simp.py` exists + benchmark assertion |
| 1.2  | 模态 / 特征频率 TO | 6 | `core/modal.py` + eigenvalue test |
| 1.3  | 几何非线性 TO | 5 | `core/nonlinear_simp.py` + Gere benchmark |
| 1.4  | 多材料 ordered SIMP | 5 | `core/multi_material.py` + bimaterial benchmark |
| 1.5  | 随机 / 可靠性 TO (Monte Carlo) | 4 | `core/stochastic.py` + uncertainty benchmark |
| 1.6  | 频响 / harmonic-driven TO | 4 | `core/freq_response.py` + freq-domain benchmark |

## §2 Coupled solvers + analytical verification (15 pts)

| Code | Item | Pts | Mechanism |
|------|------|-----|-----------|
| 2.1  | 热传导解析解 1D 杆校验 | 4 | test compares to closed-form T(x) |
| 2.2  | Euler-Bernoulli 模态频率校验 | 4 | test compares ω₁..ω₃ to formula |
| 2.3  | Gere 大变形 cantilever 校验 | 3 | test compares tip displacement to elastica solution |
| 2.4  | Mass matrix consistency (lumped vs consistent) | 2 | both backends agree on first 3 eigenvalues |
| 2.5  | Multi-physics coupling consistency | 2 | thermo-elastic test: thermal load → mechanical disp matches manual derivation |

## §3 Reliability + stochastic (15 pts)

| Code | Item | Pts | Mechanism |
|------|------|-----|-----------|
| 3.1  | Monte Carlo uncertainty quantification | 4 | `core/stochastic.uq_compliance(...)` returns mean ± std for N samples |
| 3.2  | Worst-case / minmax TO | 3 | `core/reliability.worst_case_simp(...)` + benchmark |
| 3.3  | RNG-seed reproducibility | 3 | 2 runs with same seed produce bit-exact outputs |
| 3.4  | Cross-platform stochastic fingerprint | 3 | `tests/fingerprints/stochastic_*.json` ≥ 2 entries |
| 3.5  | NSGA-II Pareto front | 2 | `core/pareto_nsga.py` + Pareto smoke test |

## §4 Engineering quality (20 pts)

| Code | Item | Pts | Mechanism |
|------|------|-----|-----------|
| 4.1  | Test count ≥ 750 | 4 | pytest --collect-only |
| 4.2  | Core coverage ≥ 95% (incl. new multi-physics modules) | 4 | pytest --cov |
| 4.3  | Property tests ≥ 25 (was 15 in v4) | 3 | grep count |
| 4.4  | Mutation kill rate ≥ 75% (v4 floor 70%, v5 raises) | 3 | `tests/mutation_report.json` |
| 4.5  | Fingerprint DB ≥ 25 (v4 ≥ 20) | 2 | count `tests/fingerprints/*.json` |
| 4.6  | Test agent extended for v5 | 2 | this file referenced in `scripts/test_agent.py` |
| 4.7  | CI runs v5 rubric | 2 | `.github/workflows/test.yml` contains `v5` step |

## §5 User-facing features (10 pts)

| Code | Item | Pts | Mechanism |
|------|------|-----|-----------|
| 5.1  | Pareto front visualisation HTML | 3 | `core/pareto_nsga.render_html(...)` |
| 5.2  | 2D→STL boundary export | 3 | `core/stl_export.write_stl(...)` + smoke test |
| 5.3  | Pure-NumPy autodiff harness | 2 | `core/autodiff.py` + gradient-check test |
| 5.4  | Multi-physics demo HTML | 2 | a benchmark produces side-by-side mechanical + thermal field |

## §6 Documentation + ADRs (10 pts)

| Code | Item | Pts | Mechanism |
|------|------|-----|-----------|
| 6.1  | blueprint-v5 six waves ticked | 2 | grep `[x]` in `docs/blueprint-v5.md` |
| 6.2  | tutorial v5 ≥ 5 new sections | 3 | `### 12.\d` or `### 13.\d` count |
| 6.3  | architecture v5 + multi-physics doc | 2 | "v5" or "multi-physics" in `docs/architecture.md` |
| 6.4  | ADRs D025-D032 ≥ 8 new | 3 | count files D025+ |

## No-regression gates (hard fail, not part of 100)

- v4 rubric must still be 100/100 (`v4_scorecard.json::total_earned == 100`)
- v3 rubric must still be 99/100
- v2 rubric must still be 97/100
- v1 rubric must still be 100/100
- **`pytest -q` must be green** — zero failures, zero errors (skips ok).
  Recorded as `pytest_check` in the scorecard. Added because the rubric
  items are static probes (file / grep / collect-count / coverage) that
  don't run the suite, so a 100/100 rubric could coexist with red pytest
  (it did — see D033). The gate runs the full suite by default;
  `--section` / `--no-pytest-gate` skip it for partial / iterative scoring.

Any regression in v1-v4 **or a red pytest suite** blocks release, even if
v5 = 100. The rubric score and the suite-green signal are independent and
both required.

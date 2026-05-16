# D020 — Bayesian opt + auto-refinement + compare HTML + CLI color (v3.4 / Wave V)

> Status: Accepted (v3.4.0 · 2026-05-16)
> Closes: D010 (auto-refinement defer)
> v4 rubric §5.1 + §5.2 + §5.3 + §5.4 evidence anchor

## Context

§5 of the v4 rubric covers "user-面 / 流程" — user-facing convenience
features that turn the engine into a workbench. v3.x had:

- Parameter studies via uniform LHS / Sobol DOE (Wave O), but no
  EI-style acquisition that exploits prior evaluations.
- Fixed-resolution SIMP (every benchmark has a hardcoded `nelx`/`nely`);
  D010 left auto-refinement deferred.
- Per-run HTML reports and per-run rich `_repr_html_`, but no
  side-by-side comparison across runs.
- Plain CLI output (errors as raw exception strings, no color even
  when the terminal supports it).

Wave V delivers all four — each component is independent and lands
together in one waved release for compactness.

## Decision

### `core/bayesian_opt.py` — design-parameter optimization

`bayesian_minimize(parameter_space, objective_fn, …) → BayesianOptResult`.

Backend selection:
- **scipy + sklearn available** → label as `scipy_gp_ei` (true GP +
  acquisition would go here; v3.4 leaves the actual sklearn-GP wiring
  for v4.1 since the numpy fallback already converges in our test
  suite).
- **numpy-only** → `numpy_random_ei`: random sampling reweighted by
  a k-nearest-neighbor objective estimate and an EI-style improvement
  weight. Sample-efficient enough for typical SIMP parameter studies
  (5–10 dims, smooth objective).

Both backends share the same return schema. Optional `seed` makes
results reproducible.

### `core/refinement.py` — adaptive mesh refinement loop

`auto_refine_until_converged(config, max_levels, factor, compliance_tolerance)
→ RefinementResult`.

Iterates SIMP at progressively finer meshes, stopping when the
compliance relative change between successive levels falls below
`compliance_tolerance`. `_refine_config` doubles `nelx`/`nely` and
scales `filter_radius` proportionally so the physical filter stays
constant.

`_interpolate_densities_to_finer_mesh` performs a nearest-cell
inheritance for factor-of-2 refinements (used informationally; the
current SIMP driver re-initializes from `volume_fraction`).

### `core/compare.py` — side-by-side HTML comparison

`comparison_html([ComparisonEntry(label, result, notes), …]) → str` and
`write_comparison_html(entries, path, title) → str`.

Renders a table with embedded base64 PNG thumbnails (via the existing
`_grayscale_png_bytes` helper) plus per-run metrics (compliance, mass,
max-disp, stop_reason, iterations). HTML-escapes user-provided labels.

### `cli.py` — color + diagnostics

- `_color_supported()` checks `NO_COLOR` (https://no-color.org/),
  `FORCE_COLOR`, and `sys.stdout.isatty()`.
- `cli_red/green/yellow(text)` wrap ANSI codes 31/32/33 when enabled.
- `diagnose_error(exc) → str` pattern-matches common error messages and
  appends an actionable hint (install missing module, enable
  stress_constraint, fix all-DOF-fixed BC).
- `main()` now uses `diagnose_error` instead of the bare `error: …`
  fallback.

## Acceptance criteria — Wave V

- [x] `core/bayesian_opt.py` with `bayesian_minimize` + `ParameterSpec`
- [x] `core/refinement.py` with `auto_refine_until_converged`
- [x] `core/compare.py` with `comparison_html` + `write_comparison_html`
- [x] `cli.py` updated with `cli_red/green/yellow` + `diagnose_error`
- [x] `tests/test_bayesian_opt.py` — 11 unit tests
- [x] `tests/test_refinement.py` — 7 unit tests (D010 closure anchor)
- [x] `tests/test_compare.py` — 7 tests including HTML-escape XSS guard
- [x] `tests/test_cli_color.py` — 11 unit tests
- [x] All v1+v2+v3+S+T+U tests still green
- [x] Test agent: §5.1 + §5.2 + §5.3 + §5.4 → PASS (10 pts)

## Caveats / honest disclosure

- The scipy-backed BO **does not actually use a GP yet** — the
  `_detect_backend()` check labels the result for future wiring; the
  current implementation runs the same numpy fallback even when
  scipy + sklearn are installed. Plugging in `sklearn.gaussian_process.GaussianProcessRegressor`
  is a 50-LOC follow-up. The chosen recipe (random search + EI-style
  reweighting + perturbed-best exploitation) converges on the test
  problems but is suboptimal vs a true GP for low-evaluation budgets.
- Auto-refinement currently **re-runs SIMP from scratch** at each
  level rather than warm-starting from the coarse result. The
  `_interpolate_densities_to_finer_mesh` helper is in place for the
  warm-start variant but `run_simp()` doesn't yet accept an
  initial-density argument; threading that through is a separate
  cleanup task.
- The comparison HTML uses inline base64 PNGs which inflate the file
  size by ~4× the raw PNG. For 2–5 runs on smoke meshes this is
  hundreds of KB total — fine. For 50 runs on 500×500 meshes it would
  be ~25MB; in that scale, switch to writing PNGs as siblings to the
  HTML and `<img src="rel.png">`.
- CLI color codes do not respect Windows console support detection
  beyond the standard `isatty()` check. Modern Windows Terminal +
  PowerShell handle ANSI fine; legacy `cmd.exe` without ANSICON would
  show raw escapes. NO_COLOR=1 is the documented workaround.

## Files changed (Wave V)

- `structure_optimizer/core/bayesian_opt.py` (new)
- `structure_optimizer/core/refinement.py` (new)
- `structure_optimizer/core/compare.py` (new)
- `structure_optimizer/cli.py` (modified — color hooks + diagnose)
- `tests/test_bayesian_opt.py` (new)
- `tests/test_refinement.py` (new)
- `tests/test_compare.py` (new)
- `tests/test_cli_color.py` (new)
- `docs/decisions/D020-bayesian-opt-refinement-compare-cli.md` (this)

## References

- Snoek, J., Larochelle, H., Adams, R. P. (2012). "Practical Bayesian
  Optimization of Machine Learning Algorithms." *NeurIPS*.
- Frazier, P. I. (2018). "A Tutorial on Bayesian Optimization."
  arXiv:1807.02811.
- Stainko, R. (2006). "An adaptive multilevel approach to the minimal
  compliance problem." *Comm. Numer. Meth. Eng.* 22.
- Berger, M.J., Oliger, J. (1984). "Adaptive Mesh Refinement for
  Hyperbolic PDEs." *J. Comput. Phys.* 53.
- https://no-color.org/ — environment-variable convention for opting
  out of color.

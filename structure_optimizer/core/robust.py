"""Wave U: Heaviside / robust three-field formulation for SIMP.

The standard SIMP filter projects the design field ``ρ`` to a smoothed
field ``ρ̃`` that suppresses checkerboarding. The resulting ``ρ̃`` is
**gray** at the design boundary (intermediate densities), which:

1. Misrepresents the realized manufactured structure (which is binary
   solid/void).
2. Makes the compliance prediction overly optimistic — when you binarize
   the design for fabrication you lose stiffness the optimizer assumed.

The **Heaviside three-field projection** (Wang/Lazarov/Sigmund 2011,
Sigmund 2007) addresses both. Define a smoothed Heaviside step around
threshold η ∈ (0, 1) with sharpness β:

    H_η,β(ρ̃) = (tanh(β·η) + tanh(β·(ρ̃ - η))) / (tanh(β·η) + tanh(β·(1 - η)))

The **robust formulation** evaluates the SIMP objective on **three
fields** simultaneously:

- "eroded" with η_e > 0.5  (worst-case material removal — most
  conservative on safety; pushes thicker minimum members)
- "nominal" with η_n = 0.5
- "dilated" with η_d < 0.5 (extra-material; matches additive
  manufacturing over-deposition)

The optimizer minimizes the **worst-case** compliance (max-of-three) so
the design is robust to projection-threshold uncertainty. This produces
near-binary, manufacturable structures with guaranteed minimum-member
size.

Reference:
    Wang, F., Lazarov, B. S., Sigmund, O. (2011). "On projection
        methods, convergence and robust formulations in topology
        optimization", *Struct. Multidisc. Optim.* 43, 767-784.
    Sigmund, O. (2007). "Morphology-based black and white filters for
        topology optimization", *Struct. Multidisc. Optim.* 33, 401-424.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HeavisideParams:
    """Threshold + sharpness for one Heaviside field.

    ``eta`` ∈ (0, 1) sets the projection threshold; ``beta`` controls
    sharpness (β→0 → identity; β→∞ → exact step). Typical schedule:
    start β=1, ramp toward β=20-40 over outer iterations to encourage
    convergence to binary.
    """

    eta: float
    beta: float = 1.0


def heaviside_project(rho_tilde: np.ndarray, params: HeavisideParams) -> np.ndarray:
    """Apply the smoothed Heaviside projection elementwise.

    H_η,β(ρ̃) = (tanh(β η) + tanh(β (ρ̃ - η))) / (tanh(β η) + tanh(β (1 - η)))

    Bounded in [0, 1] for ρ̃ ∈ [0, 1].
    """
    eta = params.eta
    beta = params.beta
    if beta < 1e-9:
        # Degenerate: return identity to avoid 0/0
        return rho_tilde.copy()
    num = np.tanh(beta * eta) + np.tanh(beta * (rho_tilde - eta))
    den = np.tanh(beta * eta) + np.tanh(beta * (1.0 - eta))
    return num / den


def heaviside_project_grad(rho_tilde: np.ndarray, params: HeavisideParams) -> np.ndarray:
    """Compute ∂H_η,β/∂ρ̃ elementwise.

    Derivative of the smoothed Heaviside used for chain-rule sensitivity
    propagation::

        ∂H/∂ρ̃ = β · (1 - tanh(β(ρ̃ - η))²) / (tanh(βη) + tanh(β(1-η)))
    """
    eta = params.eta
    beta = params.beta
    if beta < 1e-9:
        return np.ones_like(rho_tilde)
    sech2 = 1.0 - np.tanh(beta * (rho_tilde - eta)) ** 2
    den = np.tanh(beta * eta) + np.tanh(beta * (1.0 - eta))
    return beta * sech2 / den


@dataclass(frozen=True)
class RobustFields:
    """The three projected fields: eroded / nominal / dilated."""

    eroded: np.ndarray
    nominal: np.ndarray
    dilated: np.ndarray


def project_robust_fields(
    rho_tilde: np.ndarray,
    eta_eroded: float = 0.6,
    eta_dilated: float = 0.4,
    beta: float = 1.0,
) -> RobustFields:
    """Project a smoothed design field to the three robust fields.

    ``η_eroded > 0.5`` and ``η_dilated < 0.5`` are the conventional choices;
    ``η_nominal = 0.5`` is fixed.
    """
    if not (0.0 < eta_dilated < 0.5 < eta_eroded < 1.0):
        raise ValueError(
            f"thresholds must satisfy 0 < eta_dilated ({eta_dilated}) < 0.5 < eta_eroded ({eta_eroded}) < 1; got"
        )
    return RobustFields(
        eroded=heaviside_project(rho_tilde, HeavisideParams(eta=eta_eroded, beta=beta)),
        nominal=heaviside_project(rho_tilde, HeavisideParams(eta=0.5, beta=beta)),
        dilated=heaviside_project(rho_tilde, HeavisideParams(eta=eta_dilated, beta=beta)),
    )


def worst_case_compliance(
    compliance_per_field: dict[str, float],
) -> tuple[str, float]:
    """Return ``(field_name, max_compliance)`` — the worst-case among three.

    Used by the outer SIMP loop to pick which field's gradient to apply
    in the current iteration (the field with the worst compliance is the
    binding constraint).
    """
    field, value = max(compliance_per_field.items(), key=lambda kv: kv[1])
    return field, float(value)


def beta_schedule(
    iteration: int,
    initial: float = 1.0,
    target: float = 32.0,
    ramp_iterations: int = 50,
) -> float:
    """Continuation schedule for ``β`` — ramps from ``initial`` to ``target``.

    Linear interpolation in log-space, clamped at ``target`` after
    ``ramp_iterations``. Standard practice in the literature
    (Wang/Lazarov/Sigmund 2011) doubles β every 30-50 iterations.
    """
    if iteration <= 0:
        return initial
    if iteration >= ramp_iterations:
        return target
    log_b = np.log(initial) + (np.log(target) - np.log(initial)) * (iteration / ramp_iterations)
    return float(np.exp(log_b))

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import copy
import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when a benchmark configuration is invalid."""


@dataclass(frozen=True)
class MeshConfig:
    type: str
    nelx: int
    nely: int
    width: float | None = None
    height: float | None = None
    void_regions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MaterialConfig:
    young_modulus: float
    poisson_ratio: float
    density: float


@dataclass(frozen=True)
class OptimizationConfig:
    objective: str
    volume_fraction: float
    penalty: float
    filter_radius: float
    max_iterations: int
    change_tolerance: float
    min_iterations: int = 1
    min_density: float = 0.001


@dataclass(frozen=True)
class DesignSpaceConfig:
    frozen_solid: list[dict[str, Any]] = field(default_factory=list)
    void: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class SymmetryConstraintConfig:
    axis: str  # 'x' for mirror across vertical line, 'y' for horizontal line
    position: float = 0.5  # normalized [0, 1]


@dataclass(frozen=True)
class ExtrusionConstraintConfig:
    axis: str  # 'x' = uniform along x (varies in y); 'y' = uniform along y (varies in x)


@dataclass(frozen=True)
class ManufacturingConstraintsConfig:
    """v0.6 manufacturing constraints applied during optimization.

    All fields optional; absence means no constraint applied. Compatible with
    earlier configs that omit ``manufacturing_constraints`` entirely.
    """

    symmetry: SymmetryConstraintConfig | None = None
    extrusion: ExtrusionConstraintConfig | None = None
    min_member_size: float | None = None  # length, same units as mesh.width/height


@dataclass(frozen=True)
class LoadCaseConfig:
    name: str
    weight: float
    loads: list[dict[str, Any]]


@dataclass(frozen=True)
class BenchmarkConfig:
    name: str
    dimension: str
    units: str
    mesh: MeshConfig
    material: MaterialConfig
    boundary_conditions: list[dict[str, Any]]
    loads: list[dict[str, Any]]
    optimization: OptimizationConfig
    design_space: DesignSpaceConfig = field(default_factory=DesignSpaceConfig)
    load_cases: list[LoadCaseConfig] = field(default_factory=list)
    manufacturing_constraints: ManufacturingConstraintsConfig = field(default_factory=ManufacturingConstraintsConfig)
    thickness: float = 1.0
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("source_path", None)
        return data


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(updated.get(key), dict):
            updated[key] = _deep_update(updated[key], value)
        else:
            updated[key] = copy.deepcopy(value)
    return updated


def load_config(path: Path | str, preset: str | None = None) -> BenchmarkConfig:
    path = Path(path)
    raw = json.loads(path.read_text())
    presets = raw.pop("presets", {})
    if preset:
        if preset not in presets:
            raise ConfigError(f"Unknown preset '{preset}' for benchmark '{raw.get('name', path.stem)}'")
        raw = _deep_update(raw, presets[preset])
    config = parse_config(raw, source_path=str(path))
    validate_config(config)
    return config


def parse_config(raw: dict[str, Any], source_path: str | None = None) -> BenchmarkConfig:
    try:
        mesh = MeshConfig(**raw["mesh"])
        material = MaterialConfig(**raw["material"])
        optimization = OptimizationConfig(**raw["optimization"])
        design_space = DesignSpaceConfig(**raw.get("design_space", {}))
        load_cases = [
            LoadCaseConfig(name=str(case["name"]), weight=float(case.get("weight", 1.0)), loads=list(case["loads"]))
            for case in raw.get("load_cases", [])
        ]
        manufacturing_constraints = _parse_manufacturing_constraints(raw.get("manufacturing_constraints", {}))
        return BenchmarkConfig(
            name=raw["name"],
            dimension=raw["dimension"],
            units=raw["units"],
            thickness=float(raw.get("thickness", 1.0)),
            mesh=mesh,
            material=material,
            boundary_conditions=list(raw["boundary_conditions"]),
            loads=list(raw.get("loads", [])),
            optimization=optimization,
            design_space=design_space,
            load_cases=load_cases,
            manufacturing_constraints=manufacturing_constraints,
            source_path=source_path,
        )
    except KeyError as exc:
        raise ConfigError(f"Missing required config field: {exc.args[0]}") from exc
    except TypeError as exc:
        raise ConfigError(f"Invalid config structure: {exc}") from exc


def _parse_manufacturing_constraints(raw: dict[str, Any]) -> ManufacturingConstraintsConfig:
    if not isinstance(raw, dict):
        raise ConfigError("manufacturing_constraints must be an object")
    symmetry_raw = raw.get("symmetry")
    extrusion_raw = raw.get("extrusion")
    min_member_size = raw.get("min_member_size")

    symmetry = None
    if symmetry_raw is not None:
        if not isinstance(symmetry_raw, dict):
            raise ConfigError("manufacturing_constraints.symmetry must be an object")
        symmetry = SymmetryConstraintConfig(
            axis=str(symmetry_raw.get("axis", "")),
            position=float(symmetry_raw.get("position", 0.5)),
        )

    extrusion = None
    if extrusion_raw is not None:
        if not isinstance(extrusion_raw, dict):
            raise ConfigError("manufacturing_constraints.extrusion must be an object")
        extrusion = ExtrusionConstraintConfig(axis=str(extrusion_raw.get("axis", "")))

    if min_member_size is not None:
        min_member_size = float(min_member_size)

    return ManufacturingConstraintsConfig(
        symmetry=symmetry,
        extrusion=extrusion,
        min_member_size=min_member_size,
    )


def validate_config(config: BenchmarkConfig) -> None:
    if config.dimension not in {"2d", "2.5d"}:
        raise ConfigError("dimension must be '2d' or '2.5d'")
    if config.mesh.type != "structured_quad":
        raise ConfigError("only structured_quad meshes are supported in v0.1")
    if config.mesh.nelx <= 0 or config.mesh.nely <= 0:
        raise ConfigError("mesh nelx and nely must be positive integers")
    if config.mesh.width is not None and config.mesh.width <= 0:
        raise ConfigError("mesh width must be positive")
    if config.mesh.height is not None and config.mesh.height <= 0:
        raise ConfigError("mesh height must be positive")
    if config.thickness <= 0:
        raise ConfigError("thickness must be positive")
    if config.material.young_modulus <= 0:
        raise ConfigError("young_modulus must be positive")
    if not (-0.95 < config.material.poisson_ratio < 0.5):
        raise ConfigError("poisson_ratio must be in (-0.95, 0.5)")
    if config.material.density <= 0:
        raise ConfigError("density must be positive")
    if not config.boundary_conditions:
        raise ConfigError("at least one boundary condition is required")
    if not config.loads and not config.load_cases:
        raise ConfigError("at least one load is required")

    opt = config.optimization
    if opt.objective != "min_compliance":
        raise ConfigError("only min_compliance objective is supported in v0.1")
    if not (0 < opt.volume_fraction <= 1):
        raise ConfigError("volume_fraction must be in (0, 1]")
    if opt.penalty <= 0:
        raise ConfigError("penalty must be positive")
    if opt.filter_radius <= 0:
        raise ConfigError("filter_radius must be positive")
    if opt.max_iterations <= 0:
        raise ConfigError("max_iterations must be positive")
    if opt.min_iterations <= 0 or opt.min_iterations > opt.max_iterations:
        raise ConfigError("min_iterations must be in [1, max_iterations]")
    if opt.change_tolerance <= 0:
        raise ConfigError("change_tolerance must be positive")
    if not (0 < opt.min_density < 1):
        raise ConfigError("min_density must be in (0, 1)")

    for bc in config.boundary_conditions:
        _validate_selector_record(bc, "boundary condition")
        components = set(bc.get("components", []))
        if not components or not components <= {"ux", "uy"}:
            raise ConfigError("boundary condition components must be a non-empty subset of ux, uy")
    for load in config.loads:
        _validate_selector_record(load, "load")
        if float(load.get("fx", 0.0)) == 0.0 and float(load.get("fy", 0.0)) == 0.0:
            raise ConfigError("load must define nonzero fx or fy")
    for load_case in config.load_cases:
        if not load_case.name:
            raise ConfigError("load case name must be non-empty")
        if load_case.weight <= 0:
            raise ConfigError("load case weight must be positive")
        if not load_case.loads:
            raise ConfigError("load case must define at least one load")
        for load in load_case.loads:
            _validate_selector_record(load, "load case load")
            if float(load.get("fx", 0.0)) == 0.0 and float(load.get("fy", 0.0)) == 0.0:
                raise ConfigError("load case load must define nonzero fx or fy")
    _validate_design_space(config.design_space)
    _validate_manufacturing_constraints(config.manufacturing_constraints)


def _validate_selector_record(record: dict[str, Any], label: str) -> None:
    selector = record.get("selector")
    if not isinstance(selector, str) or not selector:
        raise ConfigError(f"{label} requires a non-empty selector")


def _validate_design_space(design_space: DesignSpaceConfig) -> None:
    for label, regions in (("frozen_solid", design_space.frozen_solid), ("void", design_space.void)):
        if not isinstance(regions, list):
            raise ConfigError(f"design_space.{label} must be a list")
        for region in regions:
            if not isinstance(region, dict):
                raise ConfigError(f"design_space.{label} regions must be objects")
            if not region.get("name"):
                raise ConfigError(f"design_space.{label} region requires a name")
            selector = region.get("selector")
            if not isinstance(selector, (str, dict)):
                raise ConfigError(f"design_space.{label} region requires a selector")


def _validate_manufacturing_constraints(constraints: ManufacturingConstraintsConfig) -> None:
    if constraints.symmetry is not None:
        if constraints.symmetry.axis not in {"x", "y"}:
            raise ConfigError("manufacturing_constraints.symmetry.axis must be 'x' or 'y'")
        if not (0.0 <= constraints.symmetry.position <= 1.0):
            raise ConfigError("manufacturing_constraints.symmetry.position must be in [0, 1]")
    if constraints.extrusion is not None:
        if constraints.extrusion.axis not in {"x", "y"}:
            raise ConfigError("manufacturing_constraints.extrusion.axis must be 'x' or 'y'")
    if constraints.min_member_size is not None and constraints.min_member_size <= 0:
        raise ConfigError("manufacturing_constraints.min_member_size must be positive")


def effective_load_cases(config: BenchmarkConfig) -> list[LoadCaseConfig]:
    if config.load_cases:
        return config.load_cases
    return [LoadCaseConfig(name="primary", weight=1.0, loads=config.loads)]

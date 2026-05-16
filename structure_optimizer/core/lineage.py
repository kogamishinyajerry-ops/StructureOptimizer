"""Wave O: design-lineage tracking.

Each run can record a ``parent_id`` (the run it was derived from), a
``study_id`` (the study it was a candidate of), and a ``generation``
counter. This produces a lineage tree per study + lets users trace
"derived from candidate_007" relationships across the runs/ tree.

Schema (``lineage.json`` per run):

    {
      "run_id": "20260516-220000-123456",
      "parent_id": "20260516-215012-987654" | null,
      "study_id": "cantilever_20260516-..." | null,
      "generation": 0
    }

Schema (``lineage_tree.json`` per study dir):

    {
      "study_id": "cantilever_...",
      "nodes": [
        {"run_id": "...", "candidate_id": "candidate_001", "parent_id": null, "generation": 0},
        ...
      ],
      "edges": [
        {"from": "candidate_001", "to": "candidate_005"}, ...
      ]
    }

Edges are derived from parent_id pointers; for an "all-fresh" study (LHS,
Sobol, grid) there are no edges — the tree is a forest of single nodes.
For a refinement study (each new candidate derives from a previously
ranked one) the tree shows multi-generation lineage.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class LineageRecord:
    """One run's lineage entry."""

    run_id: str
    parent_id: str | None = None
    study_id: str | None = None
    generation: int = 0


def write_lineage(run_dir: Path, record: LineageRecord) -> None:
    """Persist ``lineage.json`` in the run dir."""
    (run_dir / "lineage.json").write_text(json.dumps(asdict(record), indent=2, sort_keys=True) + "\n")


def read_lineage(run_dir: Path) -> LineageRecord | None:
    """Read ``lineage.json`` if present; ``None`` if the run pre-dates Wave O."""
    path = run_dir / "lineage.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    return LineageRecord(
        run_id=str(raw["run_id"]),
        parent_id=raw.get("parent_id"),
        study_id=raw.get("study_id"),
        generation=int(raw.get("generation", 0)),
    )


def build_lineage_tree(study_dir: Path) -> dict:
    """Walk a study dir's candidate_* subdirs, collect lineage records, return a
    JSON-serialisable tree (list of nodes + list of edges).

    Edges are computed from parent_id pointers using ``candidate_id`` (the
    sub-directory name) as the node label. Run-time IDs (timestamps) are
    kept on the nodes for traceability into runs/.
    """
    nodes = []
    parent_lookup: dict[str, str] = {}  # run_id -> candidate_id
    for sub in sorted(study_dir.iterdir()):
        if not sub.is_dir() or not sub.name.startswith("candidate_"):
            continue
        record = read_lineage(sub)
        if record is None:
            continue
        nodes.append(
            {
                "candidate_id": sub.name,
                "run_id": record.run_id,
                "parent_id": record.parent_id,
                "generation": record.generation,
            }
        )
        parent_lookup[record.run_id] = sub.name

    edges = []
    for node in nodes:
        if node["parent_id"] and node["parent_id"] in parent_lookup:
            edges.append({"from": parent_lookup[node["parent_id"]], "to": node["candidate_id"]})

    return {
        "study_id": study_dir.name,
        "nodes": nodes,
        "edges": edges,
    }


def write_lineage_tree(study_dir: Path, tree: dict) -> None:
    """Write the lineage tree JSON to ``<study_dir>/lineage_tree.json``."""
    (study_dir / "lineage_tree.json").write_text(json.dumps(tree, indent=2, sort_keys=True) + "\n")

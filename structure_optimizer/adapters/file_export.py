from pathlib import Path


class FileExporter:
    """Small boundary for future mesh/CAD exporters."""

    def export(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

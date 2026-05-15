from typing import Protocol


class Optimizer(Protocol):
    def run(self):
        """Run an optimization and return an implementation-specific result."""

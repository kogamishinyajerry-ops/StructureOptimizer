from typing import Protocol


class Solver(Protocol):
    def solve(self):
        """Solve an analysis model and return an implementation-specific result."""


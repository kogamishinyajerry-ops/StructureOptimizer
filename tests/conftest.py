"""pytest configuration shared across the test suite.

Currently only registers the ``--run-slow`` option used by Wave-N performance
tests. Other tests are unaffected.
"""

from __future__ import annotations


def pytest_addoption(parser):  # type: ignore[no-untyped-def]
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="run tests marked as slow (>5s, e.g. 500×500 mesh capability)",
    )

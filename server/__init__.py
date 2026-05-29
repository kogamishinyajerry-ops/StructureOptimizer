"""FastAPI web backend for the StructureOptimizer workbench.

Thin streaming layer over the numpy engine: exposes built-in benchmarks, starts
optimization runs in a worker thread, and streams per-iteration convergence
frames (density field + metrics) over a WebSocket so the React frontend can
render the topology emerging live.

The engine package (``structure_optimizer``) is imported, never modified here —
the only engine change this depends on is the optional ``on_iteration`` callback
threaded through ``run_simp`` / ``run_config`` (observational, default-off).
"""

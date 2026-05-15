# StructureOptimizer 性能基线

> 自动生成产物。重新生成：`python -m scripts.benchmark_performance`
> 这些数值与机器、Python 版本、NumPy BLAS 后端紧密相关。**请勿当作绝对指标**——它们的价值在于"同一台机器上的相对趋势"。

- 生成时间：2026-05-16T02:48:18
- 平台：macOS-26.3.1-arm64-arm-64bit
- Python：3.12.13
- 解释器：/Users/Zhuanz/.local/bin/python

## Smoke preset 实测

| Benchmark | Preset | Mesh | Max Iter | Wall (s) | ΔRSS (MB) | Verification |
|---|---|---|---:|---:|---:|---|
| cantilever | smoke | 24×10 | 8 | 0.16 | 10.3 | passed |
| l_bracket | smoke | 20×20 | 8 | 0.35 | 17.8 | passed |
| loaded_hook | default | 36×36 | 50 | 10.62 | 175.1 | passed |
| mbb_beam | smoke | 30×10 | 10 | 0.24 | 0.1 | passed |
| simple_bracket | smoke | 24×12 | 8 | 0.23 | 0.0 | passed |

总累计 ΔRSS：203.3 MB（受 numpy 缓存影响，仅供参考）

## 解读

- **Wall (s)** 是 `run_config()` 全流水线时间（含 mesh / SIMP 主循环 / verify / report / 可视化 PNG/GIF 落盘）。
- **ΔRSS (MB)** 是单次基准前后进程峰值常驻内存差；不是绝对内存占用，受历史调用影响。
- **Verification** 列 `passed` 表示独立验证全部约束通过。任何其他值需要查对应 run 目录的 `verification.json`。
- 默认 backend = `dense`（`np.linalg.solve`）。`backend=cg` 在大网格上内存占用更低但 wall time 通常更高，可在配置中切换实测。

## v1.8 Wave H 新增：稀疏求解器实测

在 100×30 结构网格（6262 DOF）上单次 `solve_linear_elastic`：

| Backend | 单次 solve (ms) | 相对 dense |
|---|---:|---:|
| `dense` | 1112.5 | 1.0× |
| `cg` | 2918.6 | 2.6× slower（密集 K·v 主导） |
| `sparse` | 47.3 | **24× faster** |
| `sparse_cg` | 60.9 | **18× faster** |

记录条件：macOS arm64 / Python 3.13 / scipy 1.17 / 同一台机器，warm cache 后 3 次平均。

**结论**：
- `dense` 默认在 ndof ≤ 几千时仍合适（开销低、零依赖）
- 单次大型解 → 走 `sparse`（直接稀疏分解，最快）
- 受内存限制的大网格 → 走 `sparse_cg`（迭代，最低内存）
- 老 `cg` 用 dense matrix 做 matrix-vector，并不省钱；scipy CG 配 sparse 矩阵才有意义

激活：`pip install structure-optimizer[sparse]` → config `solver.backend = "sparse"` 或 `"sparse_cg"`。

## 性能扩展建议（不在 v1.0 范围）

- 大网格（≥ 200×200）建议引入 `scipy.sparse` adapter，避免 dense O(N²) 内存
- 多核：`np.linalg.solve` 已通过 LAPACK 自动用 BLAS 多线程；CG 是单线程纯 NumPy
- GPU/MPS 加速：要等真求解器适配（CalculiX / FEniCS / JAX-FEM）成熟

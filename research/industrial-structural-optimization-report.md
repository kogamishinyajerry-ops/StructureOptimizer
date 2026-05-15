# 工业部件自动化结构优化算法与软件深度调研

调研日期：2026-05-12  
适用项目：StructureOptimizer  
调研边界：结构件优化设计，重点覆盖拓扑优化、形状/尺寸优化、多目标/鲁棒优化、仿真流程自动化、工业软件与开源技术栈。本文不评价未验证的营销宣称，不把“生成好看的形状”等同于可制造、可认证、可投产的优化设计。

## 1. 执行结论

工业结构优化已经不是单一“拓扑优化按钮”的问题，而是一个从设计空间定义、载荷工况、有限元求解、优化算法、制造约束、CAD 重构、再验证到试验闭环的工程系统。当前工业主流工具分成两类：一类是 Altair OptiStruct/Inspire、Ansys、Simcenter 3D/HEEDS、SIMULIA Tosca、nTop、COMSOL、PTC Creo、Autodesk Fusion、SOLIDWORKS Simulation、MSC Apex 这类商业平台；另一类是 Dakota、OpenMDAO、pyOptSparse、Plato、OpenPISCO、Kratos、FEniCS/pyadjoint、JAX-FEM、ToPy、DTU TopOpt 代码这类开源或研究栈。

关键判断：

1. 真正可工业化的优化不是“AI 自动画结构”，而是“仿真可信度 + 优化收敛 + 制造约束 + 可追溯验证”的组合。
2. 对大多数机械结构件，最实用的路线仍然是：先做基线 FEA，再用参数/形状/拓扑优化生成候选，再做 CAD 重构和复核仿真，最后进入制造约束与试验验证。
3. 拓扑优化适合早期概念轻量化和载荷路径发现；形状/尺寸优化更适合已有 CAD 的小幅性能提升；MDO/DOE/代理模型更适合多学科、多目标、昂贵仿真的工业场景。
4. 商业平台的强项是 CAD/CAE 集成、制造约束、后处理、企业流程；开源栈的强项是透明、可研究、可组合、可嵌入自研系统。
5. StructureOptimizer 的合理切入点不应是复制完整 OptiStruct 或 Tosca，而是做一个“可信结构优化工作台”：统一问题定义、求解器适配、结果比较、验证证据和可制造性检查。底层可先接开源求解/优化库，后续再接商业求解器。

## 2. 工业结构优化问题的标准形式

典型输入：

- 几何：设计域、保留域、禁入域、装配接口、包络空间。
- 材料：弹性模量、泊松比、密度、屈服/疲劳数据、各向异性或复合材料参数。
- 工况：载荷、约束、接触、热载、振动、压力、扭矩、多载荷组合。
- 目标：最小质量、最小柔度、最大刚度、最大一阶频率、降低应力峰值、提升屈曲裕度、降低热阻、降低压降。
- 约束：位移、应力、体积分数、频率、屈曲、疲劳寿命、安全系数、制造方向、拔模、挤出、最小/最大构件尺寸、增材 overhang、机加工可达性。
- 输出：密度场、边界形状、参数组合、候选 Pareto 解、STL/3MF/PLY/CAD、验证报告。

高风险点：

- 边界条件错误会让优化结果完全无意义。
- 点载荷/点约束会造成非物理载荷路径。
- 只看静强度会漏掉疲劳、屈曲、模态、装配和制造问题。
- 拓扑结果通常不是直接可制造 CAD，需要重构和再验证。
- 应力约束拓扑优化比柔度/体积分数更难，数值稳定性和局部奇异性更敏感。

## 3. 算法谱系

| 算法家族 | 适用阶段 | 工业价值 | 局限 |
|---|---|---|---|
| 尺寸优化 sizing | 已有梁、壳、板、杆、厚度变量 | 快、稳定、容易纳入规范 | 不改变拓扑，创新空间有限 |
| 参数优化 parametric optimization | 已有 CAD 参数或设计变量 | 适合产品迭代和工程审批 | 依赖参数化质量，容易陷入局部 |
| 形状优化 shape optimization | 优化边界、孔位、曲面、应力集中 | 对现有零件改进实用 | 拓扑不变，网格变形和重网格复杂 |
| 密度法 / SIMP | 早期概念、轻量化、载荷路径发现 | 最主流拓扑优化路线，成熟度高 | 灰度单元、棋盘格、网格依赖，需要过滤和投影 |
| 均匀化 / 多尺度拓扑 | 晶格、周期单胞、材料-结构一体化 | 适合增材和功能梯度结构 | 制造、检测、材料数据库要求高 |
| 水平集 level set | 清晰边界、形状演化 | 边界质量好，适合某些多物理问题 | 拓扑变化、初始化、数值实现更复杂 |
| ESO/BESO | 离散增删材料，直观 | 工程理解容易，适合某些离散布局 | 理论和收敛性通常不如梯度法清晰 |
| MMC/MMV 显式几何 | 显式构件或孔洞参数化 | 更接近可制造几何 | 表达能力受组件模板限制 |
| MMA/SQP/IPOPT/SNOPT 等梯度优化 | 大规模连续变量约束优化 | 拓扑、形状、MDO 常用内核 | 需要可靠灵敏度和可微模型 |
| 遗传算法/粒子群/进化算法 | 非光滑、离散、多峰、黑箱问题 | 适合参数探索、多目标候选 | 样本效率低，昂贵 FEA 下成本高 |
| DOE + RSM/Kriging/代理模型 | 昂贵仿真、多学科优化 | 工业 MDO 常用，利于解释和敏感性分析 | 代理模型外推危险，需要采样策略 |
| Bayesian optimization | 样本极贵、变量中低维 | 适合高成本仿真和实验闭环 | 高维、多约束、多保真管理困难 |
| 多目标 Pareto/NSGA-II/MOPSO | 质量、刚度、频率、成本多目标 | 给决策者可选设计族 | 需要后处理和决策准则 |
| 鲁棒/RBDO/UQ | 载荷、材料、制造误差不确定 | 适合安全关键和量产 | 计算成本高，需要概率模型 |
| 可微仿真/自动微分 | 研究型、自研优化器、反问题 | 可减少手写灵敏度，适合 GPU/JAX | 工业非线性、接触、复杂 CAD 尚需验证 |
| 生成式 AI 辅助 | 概念搜索、交互式候选、几何风格迁移 | 可做设计探索和人机交互 | 不能替代 FEA、制造约束和认证证据 |

算法选型的实用规则：

- 若目标是快速发现结构载荷路径：优先 SIMP/拓扑优化。
- 若零件已有成熟 CAD 且只允许局部改动：优先参数优化或形状优化。
- 若每次仿真很贵：优先 DOE + 代理模型 + Bayesian/多目标搜索。
- 若涉及热-结构、流-固、声学等多物理：优先 MDO 框架或 COMSOL/Simcenter/Ansys 等平台。
- 若结果要进量产：必须加入制造约束、鲁棒性评估、CAD 重构和独立验证。

## 4. 商业软件生态

| 软件 | 类型 | 强项 | 适合场景 | 对 StructureOptimizer 的启发 |
|---|---|---|---|---|
| Altair OptiStruct / Inspire | 结构优化与生成式设计 | 拓扑、形貌、尺寸、制造约束成熟；OptiStruct 文档列出质量、柔度、频率、屈曲、应力等响应 | 汽车、航空、机械轻量化 | 工业级拓扑优化的标杆，应学习其“响应函数 + 约束 + 制造约束”问题建模 |
| Ansys Mechanical / Discovery Topology Optimization | 结构仿真集成拓扑优化 | 交互式、实时设计探索、制造要求控制 | 已在 Ansys 体系内的工程团队 | 交互式反馈和轻量化体验值得借鉴 |
| Ansys optiSLang | PIDO/RDO | 流程自动化、DOE、敏感性、鲁棒优化、UQ、ROM | 多工具、多工况、多参数优化 | 可作为“流程编排与结果追踪”的竞品参照 |
| Siemens Simcenter 3D | CAE + 优化 | 拓扑优化、FE 参数优化、设计空间探索、Teamcenter 数据管理 | 企业级仿真和 PLM 集成 | 后续企业化要考虑数据管理和仿真可追溯 |
| Siemens HEEDS | MDAO/设计空间探索 | 自动工作流、分布式执行、SHERPA 混合搜索、多学科 | CAD/CAE 多工具联合优化 | StructureOptimizer 可先实现轻量版工作流编排和 Pareto 对比 |
| Dassault SIMULIA Tosca | 结构/流体优化 | shape、bead、sizing、topology，与 Abaqus 体系协同 | 非线性、真实仿真驱动优化 | 强调“基于真实仿真而非简化模型”的工业路线 |
| SIMULIA Isight | PIDO/MDO | DOE、优化、近似模型、Six Sigma、流程自动化 | 企业仿真流程自动化 | 说明优化平台不仅要算，还要管理流程 |
| COMSOL Optimization Module | 多物理优化 | 参数、形状、拓扑优化；可与结构、声学、热、流、电磁等模块组合 | 多物理组件优化 | 多物理可作为中长期方向，短期不宜自研过宽 |
| nTop Field Optimization | 隐式几何、晶格、多尺度 | field-driven design、壳/晶格厚度优化、隐式几何后处理 | 增材制造、晶格、医用植入物、航空轻量化 | 隐式几何和 field 数据模型是未来结构优化的重要方向 |
| PTC Creo Generative Design | CAD 内生成式拓扑 | 本地拓扑优化，制造要求包括 CNC、模具、铸造、锻造、增材 | Creo 用户的 CAD 内设计 | 优化结果要被设计师当 CAD 几何继续编辑 |
| Autodesk Fusion / Inventor Nastran | CAD/CAM/CAE + 生成式设计 | 云端设计探索、制造方式比较、CAD 工作流 | 中小团队和产品设计 | 生成式设计应输出可比较候选，不是单一答案 |
| SOLIDWORKS Simulation Topology Study | CAD 内拓扑优化 | 单体零件，刚度/重量、质量、位移目标；适合 SW 用户 | 机械设计师早期轻量化 | 明确了“单体固体零件”这类实用边界 |
| MSC Apex Generative Design | 生成式设计/MSC 生态 | 拓扑优化、自动网格、平滑、Mesh2CAD、可打印件 | 增材制造和 MSC 用户 | CAD 重构/mesh-to-CAD 是工业落地核心难点 |
| ESTECO modeFRONTIER | PIDO/MDO | 厂商无关，连接第三方 CAD/CAE，DOE、ROM、AI data-driven、MDO | 多学科、多目标流程优化 | 可借鉴“厂商中立优化编排器”的定位 |

商业软件共同趋势：

- 从单次拓扑优化转向设计空间探索、流程自动化、鲁棒性和数据管理。
- 从“网格结果”转向“可编辑 CAD/隐式几何/可制造输出”。
- 从单学科静力问题扩展到热、流、声、疲劳、模态、多物理。
- 从本地单机转向 HPC/云/分布式执行。
- 从专家工具逐步包装成设计师可用的交互式工作台，但核心可信度仍依赖仿真建模。

## 5. 开源与研究技术栈

| 工具 | 类型 | 可用价值 | 主要风险 |
|---|---|---|---|
| Dakota | 优化/UQ/参数研究框架 | 适合仿真黑箱优化、校准、风险分析、UQ | 不是结构 FEA 求解器，需要接外部仿真 |
| OpenMDAO | MDAO Python 框架 | 适合多学科耦合、解析导数、梯度优化、航空系统设计 | 建模门槛高，需要工程化封装 |
| pyOptSparse | 非线性约束优化框架 | 稀疏大规模优化，能接 SNOPT/IPOPT/ParOpt 等 | 部分强优化器是商业或需单独安装 |
| Plato | Sandia 拓扑优化平台 | 面向 HPC 拓扑优化，开源版本可用 | 授权和前端形态需确认，工程接入成本高 |
| OpenPISCO | 开源拓扑优化平台 | GUI/CLI/Python 库，支持网格、隐式建模、Code_Aster/FreeFem++ 接口 | R&D 属性强，工业成熟度需实测 |
| Kratos Multiphysics | 并行多物理仿真框架 | C++/Python、结构/流体/FSI/优化应用，BSD 许可 | 架构复杂，学习和构建成本高 |
| FEniCS + pyadjoint/dolfin-adjoint | PDE/自动伴随 | 灵敏度、最优控制、设计优化研究好用 | CAD/工业前后处理弱，生态正在迁移 |
| JAX-FEM | 可微 FEM/GPU/JAX | 自动微分、逆设计、拓扑优化实验 | GPL-3.0，工业闭源产品要注意许可 |
| ToPy | Python 拓扑优化教育框架 | 轻量、2D/3D compliance/heat/mechanism 示例 | 老项目，稳定版 Python 2，生产不适合 |
| DTU TopOpt 99/88-line/top99neo | 教学和基准代码 | 理解 SIMP、过滤、MBB beam 的最佳入口 | 教学代码，不是工业求解平台 |
| FreeCAD/CalculiX/Code_Aster/Gmsh/Meshio | 开源 CAD/FEA/网格链条 | 可作为验证、网格、开源求解器基础 | 集成和鲁棒性工作量大 |
| SU2/OpenFOAM adjoint | PDE/CFD 优化 | 适合流体/气动形状优化 | 不适合作为第一阶段结构件 MVP 主线 |

开源路线建议：

1. 第一阶段不要一上来接复杂 CAD。先用规范化基准问题和简单几何域把优化闭环跑通。
2. 优化内核可从 pyOptSparse / SciPy / NLopt / Dakota / OpenMDAO 中选择，但必须用统一 adapter 层隔离。
3. 结构分析可从轻量自研 2D FEM 或 FEniCS/JAX-FEM 试验开始，再引入 CalculiX/Code_Aster/Kratos 做验证。
4. 结果后处理优先输出 VTK/STL/3MF + 设计变量历史 + 收敛曲线，不急于做高质量 NURBS。
5. 许可必须前置审查：GPL、LGPL、BSD、商业优化器、政府许可证不能混用到不清不楚。

## 6. 工业工作流

一个可信的结构优化流程应至少包含：

1. 需求冻结：部件功能、装配接口、不可动区域、可动区域、材料、制造方式、载荷包络。
2. 基线模型：导入 CAD/网格，建立基线 FEA，保存应力、位移、质量、模态等基线指标。
3. 优化问题定义：目标函数、约束、设计变量、体积分数、制造约束、收敛条件。
4. 优化运行：记录每轮目标、约束、设计变量、网格、求解器日志、失败原因。
5. 候选筛选：按质量、刚度、应力、频率、制造成本、可编辑性排序。
6. 几何重构：密度场/网格结果平滑，生成可制造几何；必要时人工 CAD 重构。
7. 独立验证：对重构后的几何重新网格、重新 FEA，比较优化前后指标。
8. 制造评估：增材支撑、overhang、热变形、机加工可达性、铸造拔模、壁厚、孔洞清理。
9. 鲁棒性检查：载荷扰动、材料离散、制造公差、多工况包络。
10. 实物验证：样件、静载、疲劳、振动、热循环，形成设计冻结证据。

最容易被忽略的不是算法，而是第 1、2、6、7、8 步。很多“自动优化”失败，是因为输入工况不可信、结果无法制造或重构后性能丢失。

## 7. 对 StructureOptimizer 的产品架构建议

建议定位：结构优化可信工作台，而不是单一优化算法库。

核心对象模型：

- `Project`：项目元数据、单位制、版本、材料库、制造路线。
- `GeometrySet`：设计域、保留域、禁入域、装配接口、基线 CAD/mesh。
- `LoadCase`：载荷、约束、组合系数、工况说明、来源证据。
- `FEModel`：网格、单元类型、材料映射、求解器配置。
- `OptimizationProblem`：变量、目标、约束、算法、制造限制、收敛准则。
- `Run`：一次优化运行，包含输入 hash、求解器日志、迭代历史、失败状态。
- `CandidateDesign`：候选几何、指标、图像、文件、Pareto 排名。
- `VerificationReport`：重构后 FEA、对比基线、通过/失败、人工备注。
- `AuditTrail`：每次输入变更、参数变更、结果导出和验证命令。

模块划分：

- Problem Builder：结构化定义设计域、载荷、目标和约束。
- Solver Adapter：统一调用 FEM/商业求解器/开源求解器。
- Optimizer Adapter：统一调用 MMA/SciPy/pyOptSparse/Dakota/OpenMDAO。
- Result Store：保存每轮迭代、字段、收敛、文件和图像。
- Candidate Explorer：候选设计对比、Pareto 图、指标排序。
- Verification Runner：对候选几何做独立复核分析。
- Manufacturability Checker：最小壁厚、overhang、拔模、挤出、机加工可达性等规则。
- Report Generator：导出工程报告，包含输入、假设、结果、验证命令和风险。

最小可行技术路线：

1. MVP-0：研究基准库。实现 MBB beam、cantilever、L-bracket、loaded hook、simple bracket 的统一配置文件和结果格式。
2. MVP-1：2D/简化 3D SIMP 工作台。支持体积分数、柔度最小、密度过滤、收敛曲线、PNG/VTK 输出。
3. MVP-2：验证闭环。把优化结果重新转成网格，跑独立 FEA，输出前后质量、位移、柔度、最大应力对比。
4. MVP-3：制造约束。加入最小构件尺寸、对称、挤出方向、overhang 粗检。
5. MVP-4：外部求解器适配。接 CalculiX/Code_Aster/FEniCS 或 JAX-FEM，并保留 adapter 接口接商业软件。
6. MVP-5：工业候选对比。支持多载荷、多目标、Pareto 候选、报告导出。

不建议第一阶段做：

- 完整 CAD 内核和高质量 NURBS 重构。
- 非线性接触、疲劳、复合材料、多物理全覆盖。
- “AI 自动生成可投产零件”的宣传。
- 与 PLM/云协同/权限系统深度绑定。

## 8. 评估矩阵

建议给后续工具或算法打分时使用 1-5 分：

| 维度 | 说明 | 权重建议 |
|---|---|---:|
| FEA 可信度 | 单元、材料、边界、求解器成熟度 | 20% |
| 优化能力 | 目标/约束种类、收敛、灵敏度、规模 | 20% |
| 制造约束 | 增材、机加工、铸造、挤出、最小尺寸 | 15% |
| 几何回路 | CAD/mesh 导入导出、重构、再验证 | 15% |
| 自动化/API | 批处理、脚本、HPC、日志、可复现 | 10% |
| 可解释性 | 收敛曲线、敏感性、失败原因、审计 | 10% |
| 成本/许可 | 商业许可、开源许可、部署复杂度 | 5% |
| 学习曲线 | 工程师上手难度、文档、社区 | 5% |

## 9. 工业案例与可复用基准

建议后续用三层基准验证 StructureOptimizer：

基础教学基准：

- MBB beam：SIMP 拓扑优化经典例子。
- Cantilever beam：悬臂梁轻量化，适合验证边界条件和过滤器。
- L-bracket：应力集中和柔度优化差异明显。
- Loaded hook：COMSOL 等平台常用结构拓扑例子。

工程概念基准：

- GE engine bracket：航空支架轻量化和增材制造研究常见案例。
- NASA EXCITE bracket / A15 bracket：质量、频率、增材制造和晶格优化可用于候选对比。
- 汽车悬架 upright/control arm：多载荷、模态、疲劳、制造约束明显。
- 热沉/换热结构：热-结构/流动可作为多物理中期基准。

工业公开案例：

- Airbus 与 Autodesk 的 bionic partition 体现了生成式设计和增材制造结合，但其价值在于工程验证和制造路线，不只是形状复杂。
- Bugatti 3D printed titanium brake caliper 体现了高性能汽车部件的增材制造探索，但量产可行性取决于材料、工艺、检测和测试。
- nTop 的 NASA EXCITE bracket 案例显示 field/lattice 优化可以在质量、频率、振动载荷之间寻找平衡。

## 10. 风险与治理

工程风险：

- 工况定义不完整：单一静载优化会生成对真实工况脆弱的结构。
- 数值伪影：棋盘格、网格依赖、灰度单元、局部应力奇异。
- 后处理损失：密度场转 STL/CAD 后性能下降。
- 制造不一致：打印方向、残余应力、孔洞排粉、刀具可达性未纳入。
- 认证证据不足：优化前后缺少独立验证和试验计划。

产品风险：

- 若只做漂亮可视化，会被商业 CAD/CAE 平台快速压制。
- 若第一阶段追求全 CAD/CAE 替代，范围会失控。
- 若没有统一数据模型，后续很难接多求解器、多优化器、多候选。
- 若许可不清，开源组件会限制商业化。

治理建议：

- 每个优化结果必须带输入 hash、算法版本、求解器版本、配置文件、收敛图、复核分析结果。
- UI 文案应避免“自动保证强度”，改为“生成候选并完成验证检查”。
- 报告必须分开呈现“优化模型结果”和“重构后验证结果”。
- 对外展示要保留失败案例和约束违规原因，避免过度承诺。

## 11. 推荐路线

第一优先级：建立可信闭环。

- 先做 2D/简化 3D 基准，不先碰复杂 CAD。
- 实现 SIMP + 过滤 + 柔度最小 + 体积分数约束。
- 每个结果必须能复核，输出收敛图、密度图、验证指标。

第二优先级：建立可扩展适配器。

- 优化器 adapter：SciPy、pyOptSparse、Dakota/OpenMDAO 预留。
- 求解器 adapter：内置简化 FEM、FEniCS/JAX-FEM 实验、CalculiX/Code_Aster/Kratos 预留。
- 文件 adapter：JSON/YAML 配置、VTK/STL/3MF、后续 STEP/meshio/gmsh。

第三优先级：制造和报告。

- 先实现最小构件尺寸、对称、挤出方向、overhang 粗检。
- 生成工程报告，不只生成图片。
- 让用户能比较多个候选，而不是只拿到一个“最优答案”。

中长期方向：

- 多目标 Pareto 和 DOE/代理模型。
- 鲁棒优化和不确定性量化。
- 晶格/隐式几何/field-driven design。
- 接入商业求解器作为高保真验证后端。
- 用 LLM 做问题配置助手和报告解释，但不让 LLM 替代 FEA 判定。

## 12. 来源索引

访问日期均为 2026-05-12。

核心算法与论文：

- S1. Svanberg, "The method of moving asymptotes - a new method for structural optimization", DOI: https://doi.org/10.1002/nme.1620240207
- S2. Bendsøe and Kikuchi, "Generating optimal topologies in structural design using a homogenization method", DOI: https://doi.org/10.1016/0045-7825(88)90086-2
- S3. Allaire, Jouve and Toader, level set structural topology optimization PDF: https://www.ljll.fr/jouve/papers/jcp_final.pdf
- S4. Huang and Xie, "Advantages of Bi-Directional Evolutionary Structural Optimization (BESO) over ESO": https://journals.sagepub.com/doi/10.1260/136943307783571436
- S5. Andreassen et al., "Efficient topology optimization in MATLAB using 88 lines of code": https://link.springer.com/article/10.1007/s00158-010-0594-7
- S6. Multi-scale topology optimization review: https://link.springer.com/article/10.1007/s00158-021-02881-8

商业软件与官方资料：

- S7. Altair OptiStruct Topology Optimization documentation: https://2025.help.altair.com/2025/hwsolvers/altair_help/topics/solvers/os/topology_opt_intro_r.htm
- S8. Ansys Topology Optimization: https://www.ansys.com/applications/topology-optimization
- S9. Ansys optiSLang: https://www.ansys.com/products/connect/ansys-optislang
- S10. Siemens Simcenter 3D: https://www.siemens.com/en-gb/products/simcenter/mechanical-simulation/simcenter-3d/
- S11. Siemens Simcenter HEEDS: https://www.siemens.com/en-us/products/simcenter/integration-solutions/heeds/
- S12. Dassault SIMULIA Tosca: https://www.3ds.com/products/simulia/tosca
- S13. Dassault SIMULIA Isight: https://www.3ds.com/products/simulia/isight
- S14. COMSOL Optimization Module: https://www.comsol.com/optimization-module
- S15. nTop Field Optimization: https://www.ntop.com/software/capabilities/field-optimization/
- S16. PTC Creo Generative Design Topology Optimization: https://support.ptc.com/help/creo/creo_pma/r12/usascii/generative_design/perform_topology_optmization.html
- S17. Autodesk topology optimization: https://www.autodesk.com/solutions/topology-optimization
- S18. SOLIDWORKS Topology Study documentation: https://help.solidworks.com/2026/english/SolidWorks/cworks/c_generative_design_study.htm
- S19. MSC Apex Generative Design: https://www.cadence.com/content/cadence-www/global/en_US/home/tools/msc-software/msc-apex-gd.html
- S20. ESTECO modeFRONTIER: https://engineering.esteco.com/modefrontier/

开源与研究工具：

- S21. Dakota: https://dakota.sandia.gov/about-dakota/
- S22. OpenMDAO: https://openmdao.org/what-is-openmdao/
- S23. pyOptSparse documentation: https://mdolab-pyoptsparse.readthedocs-hosted.com/en/latest/
- S24. Sandia Plato: https://www.sandia.gov/plato3d/
- S25. OpenPISCO: https://openpisco.irt-systemx.fr/
- S26. Kratos Multiphysics: https://kratosmultiphysics.github.io/Kratos/
- S27. pyadjoint / dolfin-adjoint: https://www.dolfin-adjoint.org/en/latest/
- S28. JAX-FEM: https://github.com/deepmodeling/jax-fem
- S29. ToPy: https://github.com/williamhunter/topy

工业案例：

- S30. Airbus bionic 3D printing: https://www.airbus.com/en/newsroom/news/2016-03-pioneering-bionic-3d-printing
- S31. Bugatti 3D printed titanium brake caliper: https://newsroom.bugatti.com/press-releases/world-premiere-brake-caliper-from-3-d-printer
- S32. nTop NASA EXCITE bracket case: https://www.ntop.com/resources/blog/optimizing-the-mass-and-natural-frequency-of-the-nasa-excite-bracket-with-field-optimization/
- S33. Aerospace bracket numerical and experimental investigation: https://www.mdpi.com/2076-3417/13/24/13218


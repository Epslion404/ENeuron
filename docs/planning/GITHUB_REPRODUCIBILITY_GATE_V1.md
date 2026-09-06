# GitHub 可复现性门 V1

状态：`G0_G1_IMPLEMENTED / T1_PROTOCOL_SLICE_PROVEN / G2_REQUIRES_VIVADO`

日期：2026-09-07

## 1. 目标

保证维护者只取得 GitHub 仓库、安装文档明确列出的工具后，就能重放项目当前声明。复现不依赖本机未提交文件、临时目录、个人绝对路径、历史终端输出或口头说明。

本门不承诺不同操作系统、不同 Vivado 版本和不同实现线程数生成逐字节相同的全部日志。它要求输入、工具身份、执行入口和验收判据被固定，并把重新运行的结果与仓库内机器可读合同比较。

## 2. 当前审计结论

当前可判定为 `PARTIAL / T1_PROTOCOL_SLICE_PROVEN`：

- 从 `git archive HEAD` 解出的干净快照中，CI-Fast、NPU Oracle 和产物索引共 57 项测试通过，证明已提交基线的一部分不依赖当前工作树。
- 当前 T1 的 `npu_zynq7020_t1_wrapper.sv`、`tb_npu_zynq7020_t1_wrapper.sv` 和测试计划尚未全部进入 GitHub；wrapper 仍有未声明信号和声明顺序问题，不能编译，因此不得把 T1 写成可复现。
- 已新增 `requirements-repro.txt` 和工具链锁定文件；完整数据集重新生成仍需单独验证 scikit-learn 版本兼容性。
- Vivado runner 已支持 `-VivadoRoot` 或 `VIVADO_ROOT`；未提供参数时仍保留本机默认路径，便于当前维护机直接运行。
- 现有 OOC manifest 已绑定 RTL、Tcl、runner、报告 SHA-256、器件、时钟与 Vivado 版本；已新增 `REPRODUCE.md` 与统一检查器。
- `artifacts/README.md` 仍把当前单时钟 OOC 描述为 setup 未收敛，与 `npu_single_clock_ooc_manifest.json` 的 V2 `VIVADO_OOC_PASS` 不一致，必须修正。
- GitHub Actions 使用 `actions/checkout@v7`、`actions/setup-python@v7` 等可移动标签。GitHub 当前安全建议是使用完整 commit SHA 才能得到不可变 action 版本；实施时应锁定 SHA，并在同行注释保留对应发布标签。

## 3. 复现层级

### G0：仓库闭包

GitHub 必须包含当前声明涉及的全部源码、testbench、固定输入、期望输出、Tcl/PowerShell/Python 入口、机器可读 manifest 和说明文档。任何本地 WIP、未跟踪文件或 `.gitignore` 中的必要输入都会使该层失败。

### G1：开源功能门

在全新 clone 或 `git archive HEAD` 快照中，仅按仓库依赖文件安装 Python、Icarus Verilog 和 Yosys，然后运行统一入口。必须完成 Python 单元测试、RTL 编译/仿真、形式或证据完整性检查；不得从父工作树读取文件。

### G2：Vivado 物理门

在安装 Vivado 2024.1 的 Windows 主机上，通过 `VIVADO_ROOT` 或显式参数定位工具，不依赖个人盘符。重建时固定：

- 器件 `xc7z020clg400-1`；
- 100 MHz 时钟；
- 顶层和全部源文件；
- 综合/实现流程与线程数；
- 恰好 4 个 DSP48E1；
- setup/hold 失败端点、route error、DRC error 均为 0。

已提交报告使用 SHA-256 验证字节完整性；重新运行以机器可读判据等价为准，不要求 Vivado 日志时间戳、路径和非语义文本逐字节一致。

### G3：板级端到端门

首次板级跑通后，GitHub 还必须包含 bitstream 生成入口、约束、PS/PL 接口配置、Host 发送程序、固定模型、固定输入流、预期输出、串口或网络协议版本、板卡型号和结果 manifest。只有 G3 通过，才允许把“首次完整端到端运行”标记为可由第三方重放。

## 4. 建议批准的九项决定

### R1：单一入口（已实施）

已新增 `REPRODUCE.md` 和 `tools/repro/verify_repository.py`。当前入口检查 G0/G1，`--t1` 执行 T1 协议切片；G2 仍由 Vivado runner 单独执行。失败返回非零并列出缺失项。

### R2：机器可读环境（已实施）

新增：

- `requirements-repro.txt`：只包含重建数据与测试真正需要的 Python 依赖，并固定版本；
- `tools/repro/toolchain.lock.json`：记录 Python、Icarus、Yosys、Vivado、器件和关键 GitHub Action 的批准身份；
- 环境探针输出实际版本，版本不符时 fail closed，不静默跳过要求执行的门。

### R3：仓库输入闭包（已实施）

新增 `tools/repro/repro_manifest.json`，显式列出每个当前结论所需的源码、固定向量、runner、testbench、报告和验证器。检查器必须确认文件被 Git 跟踪、未被忽略、SHA-256 与 manifest 一致，且 manifest 不包含绝对路径或凭证。

### R4：干净快照验证

本地和 CI 都从 `git archive HEAD` 或全新 clone 创建隔离目录，再运行 G0/G1。不得直接在原工作树执行后把结果当作复现证据。检查器同时验证运行后没有偷偷修改源码或依赖仓库外文件。

### R5：T1 纳入条件（协议切片已实施）

T1 wrapper、testbench、测试计划、XPM 仿真模型修改和运行入口必须作为同一可审核变更进入 GitHub。至少完成：

- Icarus `-g2012 -Wall` 编译无 error；
- T1 合同仿真通过；
- 运行命令不写入被跟踪源码目录；
- CI 路径分类能触发 T1 对应的 Windows XPM/全仓门；
- manifest 绑定这些文件。

当前 wrapper 的协议切片已在 Icarus 12.0 下编译和运行通过；T1-01～T1-12 全覆盖仍是后续工作。

### R6：Vivado 路径去本机化（已实施）

所有 Vivado runner 优先读取 `-VivadoRoot` 或 `VIVADO_ROOT`，再做有限的标准安装路径探测；禁止把个人盘符作为唯一入口。runner 必须记录实际 `version -short`、可执行文件位置的脱敏形式、Git HEAD、工作树是否干净和命令退出码。

### R7：结果验收与防篡改分离

- 重放结果：从原始报告重新解析资源、时序、DSP、route 和 DRC 判据。
- 历史证据：从 Git 提交读取字节并核对 SHA-256。
- 禁止只相信手写摘要，也禁止因日志路径或时间戳变化否定一个判据等价的重跑。

### R8：CI 固定与本地 Vivado 分工

GitHub-hosted runner 执行 G0/G1 和已提交物理证据的完整性检查；Vivado 2024.1 因许可证和安装体积继续在受控本机运行。GitHub Actions 的外部 action 固定到完整 commit SHA，工作流权限保持 `contents: read`，不引入能访问本机 Vivado 或私钥的公共自托管 PR runner。

### R9：发布阻断

首次端到端跑通、资源裁剪版本或新的物理性能声明，在对应 G0-G3 门未通过前不得合并为“已复现”状态。CI 因账户计费未启动时只能记录 `NOT_RUN_BILLING_BLOCKED`，本地通过不能冒充同一 HEAD 的 GitHub CI 通过。

## 5. 验收标准

完成实施后，必须提供以下证据：

1. `git archive HEAD` 隔离目录中的 G0/G1 一键命令返回 0。
2. 删除 manifest 中任一必需文件、篡改一个字节、加入绝对路径或改变工具版本时，检查器均返回非零。
3. T1 文件全部被 Git 跟踪，T1 仿真由统一入口真实执行且没有 skip。
4. 在另一目录设置 `VIVADO_ROOT` 后可完成 G2，不需要修改 runner 源码。
5. G2 从报告重算得到 `xc7z020clg400-1 / 100 MHz / DSP=4 / setup=0 / hold=0 / route=0 / DRC=0`。
6. README、文档索引、artifact 索引、工作流状态和 manifest 对当前 PASS/FAIL 边界一致。
7. 所有正式证据绑定明确 Git HEAD；工作树不干净时生成正式 manifest 必须失败。

## 6. 审批边界

本文件只冻结可复现性方案，不修 T1 RTL、不改 GitHub Actions、不重跑 Vivado，也不声称当前 GitHub 已经足够复现整个 T1-T3 或板级流程。

管理员批准 R1-R9 后，才按“测试 RED → 最小实现 → 干净快照回归 → Vivado 重放 → 文档/manifest 收口”的顺序分解实施任务。

## 7. 参考依据

- GitHub Actions Secure use reference：建议第三方 action 固定到完整 commit SHA，并保持最小 `GITHUB_TOKEN` 权限。
- GitHub Actions Dependency caching reference：缓存只能用于加速，不能替代依赖锁文件和输入身份。
- AMD Vivado UG894：批处理 Tcl、显式参数和 `report_* -file` 适合把实现流程及机器报告固化为可重放入口。

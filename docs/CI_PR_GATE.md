# ENeuron PR 自动检查

## 目标

`.github/workflows/pr-gate.yml` 只做自动检查，不自动批准、不自动合并、不代替管理员做设计裁定。

每次 PR 新建、重新打开或更新提交时，工作流先分类变更，再运行固定的 `PR Gate` 汇总门。专项门按路径选择：

1. **Fast Python and diff check**：始终编译 Python、检查 Git 空白错误；只有 NPU oracle 文件变化时运行其定向单测。
2. **Full repository regression**：未知代码、通用 RTL、脚本或 workflow 变化时运行全仓单元测试。
3. **XPM CDC wrapper**：仅 XPM/异步 FIFO 相关文件变化时运行 Windows MSYS2 UCRT64 专项门。
4. **NP7 functional and evidence gate**：仅 NP7 功能源、oracle 或软件证据变化时运行完整 NP7 验证。
5. **NP7 physical evidence integrity**：仅 NP7 物理报告、manifest、物理验证器或绑定源变化时运行。
6. **PR Gate**：始终执行；允许未选中的专项门为 `skipped`，拒绝任何选中门失败。分支保护只应要求这一项。

工作流使用 `pull_request` 事件和 `contents: read` 权限。它检出 PR 的真实 head SHA，而不是 GitHub 为 PR 生成的临时 merge commit，避免证据验证出现 HEAD 不一致。

## GitHub 网页配置

### 1. 检查工作流是否出现

1. 打开仓库 `Actions` 页面。
2. 选择 `ENeuron PR Gate`。
3. 创建测试 PR 或向现有 PR 推送一个提交。
4. 确认三个 job 都能启动，并查看失败 job 的日志。

### 2. 将检查设为 main 的合并门槛

1. 打开 `Settings` → `Branches`。
2. 编辑 `main` 的 branch protection rule，或创建新的规则。
3. 勾选 **Require a pull request before merging**。
4. 勾选 **Require status checks to pass before merging**。
5. 搜索并只勾选检查名 **`PR Gate`**。
6. 建议勾选 **Require branches to be up to date before merging**，让检查基于最新 `main` 重跑。
7. 保存规则。

不要勾选“允许 GitHub Actions 绕过分支保护”，也不要把工作流改为 `pull_request_target` 来获得写权限。

## 状态如何解释

### PASS

表示该 job 的机械规则全部满足，可以进入人工审核。它不表示：

- 自动批准 PR；
- 自动合并 PR；
- 证明完整板级吞吐、以太网、DMA 或 PS 软件性能；
- 允许修改已经冻结的协议或门槛。

### FAIL

表示至少一条可重复规则失败。管理员应查看日志，再决定是修复代码、补充证据，还是提出新的决策点。工作流不会自行降低 G3、改变 B-V1+V2 或放宽 8/8 时序要求。

### Vivado 说明

GitHub 托管 runner 不包含项目所需的 Vivado。物理 job 只验证已经提交的报告是否完整、哈希是否一致、版本/主机绑定是否存在以及未收敛配置是否被正确排除。真正的 Vivado/XSim 运行仍应在安装了对应版本 Vivado 的受控机器上完成，再把可复现日志和报告提交到 PR。

## 本地复现

在仓库根目录执行与 CI 相同的核心命令：

```powershell
python -X utf8 -m compileall -q .
python -X utf8 -m unittest -v test_ci_fast_v1.py
python -X utf8 -m unittest discover -v
python -X utf8 -m unittest -v test_np7_shared_lane_oracle
python -X utf8 np7_shared_lane_cosim.py
python -X utf8 np7_three_model_integration_cosim.py
python -X utf8 np7_formal_and_mutations.py
python -X utf8 verify_np7_software_cost.py <PR_HEAD_SHA>
python -X utf8 verify_np7_physical_cost.py <PR_HEAD_SHA>
python -X utf8 test_np7_physical_mutations.py
```

Windows 默认代码页下也应保留 `-X utf8`，以避免 mutation 日志因中文输出编码失败。

## 维护规则

- 修改 gate 命令或阈值时，必须同时更新本文件和相关项目决策文档。
- 修改路径分类规则时，必须更新 `test_ci_fast_v1.py` 的矩阵，并验证未选中的专项门不会成为合并阻塞。
- GitHub 官方 JavaScript action 统一使用 Node 24 兼容主版本；当前基线为 `actions/checkout@v7`、`actions/setup-python@v7`。升级 action 主版本必须用 workflow 变更触发全量门，不允许只凭版本号替换直接合并。
- 工作流只能机械执行已冻结规则；出现产品、协议、门槛或范围选择时，必须回到 PR 请求仓库 admin 决策。
- 不在工作流中写入 token、私钥、Vivado 许可证或其他 secrets。

## Node 24 action 基线（2026-09-03）

PR #31 的 run `33789363607` 对 `actions/checkout@v4` 发出 Node.js 20 弃用警告。官方发布接口核对结果：`actions/checkout` 最新稳定版为 `v7.0.1`，`actions/setup-python` 最新稳定版为 `v7.0.0`；两者当前推荐主版本均为 `v7`。

Node 24 action 要求 runner `v2.327.1` 或更高。核对时 GitHub 官方 runner 最新稳定版为 `v2.337.0`；本项目使用 `ubuntu-latest`/`windows-latest` 托管 runner，但仍必须由本仓库的真实 workflow 全量 run 证明兼容，不能用官方版本说明代替执行证据。

`test_actions_use_node24_compatible_majors` 固定 checkout/setup-python 的使用次数并拒绝旧主版本回退。未来升级到新的主版本时，应同时更新该测试与本节记录。


## Windows 专项测试与固定工具路径（PR #6 round 6）

`test_host_bridge_xpm_wrapper.py` 依赖 Windows + MSYS2 UCRT64 专用固定路径
`C:\msys64\ucrt64\bin\iverilog.exe` 与 `vvp.exe`（仓库 admin 在 issue comment
`5506790489` 裁定允许保留，条件是所有四点注明）。因此本 gate 的平台分工是：

- `Python and syntax`（ubuntu-latest）：先 `apt-get install --no-install-recommends -y iverilog yosys`，
  让依赖 PATH 上 Icarus 的可移植测试真正执行；该 XPM 测试在 Linux 上显示
  `skipped "SKIPPED/NOT APPLICABLE: host platform is ..." **并附原因**`，不再抛 `RuntimeError`，
  作业日志里用 `UBUNTU_XPM_NOTICE_BEGIN/END` 标出这些 notice。
- `XPM CDC wrapper (Windows MSYS2 UCRT64)`（新增 `windows-xpm-cdc` 作业，windows-latest）：用
  `msys2/setup-msys2@v2`（`msystem: UCRT64`）安装 `mingw-w64-ucrt-x86_64-iverilog` 到固定路径后执行
  `python -X utf8 -m unittest -v test_host_bridge_xpm_wrapper`；**守卫步骤**规定：日志出现
  `NOT APPLICABLE` 或 `TOOLCHAIN_DEFECT` 即判该作业失败，所以“跳过”不能充当通过。
- 固定路径下的已知工具链缺陷（`-Wall` 无输出崩溃、本机 `vvp.exe` 连空 testbench 都崩溃）以及
  逐条行号对照表见 `docs/WINDOWS_MSYS2_XPM_TOOLCHAIN.md`。

维护要求：新增“只能在某个 OS/特定安装布局上跑”的测试时，必须同时提供
（1）代码与文档里的显式注明、（2）非该环境的 `SKIPPED/NOT APPLICABLE` 原因、
（3）对应 OS 的专用作业与“跳过即失败”守卫、（4）一条平台无关的用例断言前 3 项仍然存在。

补充（round 7，run `33615563208` @ `ddb24fc`）：Windows 作业显式
`location: C:\msys64`，并在 action 把 UCRT64 树装到别处时以联接/复制兜底，作业日志用
`fixed_path_source=` 记录最终来源。该 run 里固定路径 provisioning 与
`Show fixed toolchain paths and tool versions` 均成功（`iverilog.exe`/`vvp.exe` 都是
Icarus 13.0 (stable) v13_0），5 条用例真实执行，但 2 条仿真用例在 **elaborate** 阶段暴露
模型自身的缺陷：`xpm_fifo_async_sim.sv` 的 `ram_empty` 在 :77 使用、:88 才声明；MSYS2 13.0
拒绝“声明晚于使用”，而本机 `C:\iverilog` 的 12.0 (devel) 快照会静默通过。因此修复放在 RTL
侧，并新增不依赖任何外部工具的平台无关静态守卫
`test_model_declares_every_signal_before_use`（把修复前的文件放回去会立刻失败）。
三个 Icarus 构建的行为差异与修复前/后证据见 `docs/WINDOWS_MSYS2_XPM_TOOLCHAIN.md` 第 8 节、
`artifacts/logs/xpm_wrapper_icarus130_before_after.txt`、
`artifacts/logs/xpm_wrapper_ci_run_33615563208.txt`。

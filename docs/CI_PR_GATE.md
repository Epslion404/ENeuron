# ENeuron PR 自动检查

## 目标

`.github/workflows/pr-gate.yml` 只做自动检查，不自动批准、不自动合并、不代替管理员做设计裁定。

每次 PR 新建、重新打开或更新提交时，工作流运行三道门：

1. **Python and syntax**：编译全部 Python、运行仓库单元测试、检查 Git 空白错误。
2. **NP7 functional and evidence gate**：安装 Icarus/Yosys，运行 NP7 oracle、逐周期协同仿真、三模型接入、formal/mutation，并用 PR HEAD 重新验证软件证据。
3. **NP7 physical evidence integrity**：只读检查已提交的 Vivado OOC 报告、摘要、哈希和物理 mutation；不会在 GitHub 托管 runner 上调用 Vivado。

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
5. 搜索并勾选以下三个检查名：
   - `Python and syntax`
   - `NP7 functional and evidence gate`
   - `NP7 physical evidence integrity`
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
- 工作流只能机械执行已冻结规则；出现产品、协议、门槛或范围选择时，必须回到 PR 请求仓库 admin 决策。
- 不在工作流中写入 token、私钥、Vivado 许可证或其他 secrets。


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

# ENeuron 数字识别 D0 冻结报告

## 状态

`D0_PASS`：数据 fixture、分层 manifest、秩序延迟编码和 patch 掩码合同已冻结。
本阶段只验证输入数据与编码，不宣称 ENeuron 已经完成数字识别。

## 冻结参数

| 项目 | 值 |
|---|---|
| 图像尺寸 | 8×8 |
| 类别 | 0..9，共 10 类 |
| 像素量化 | 0..15 |
| 编码 | rank-order latency |
| 每图选中像素 | K=16 |
| 时间窗 | 16 tick |
| 每图事件数 | 恰好 16 |
| patch | 2×2，共 16 个 |
| 每个 patch 输入 | 4-bit mask |
| split seed | 20260819 |

## 数据统计

- fixture 样本数：1797
- train：1252
- validation：270
- test：275
- 三个 split 互不相交，且每个 split 都包含 10 个类别。
- fixture SHA-256：`6fa95b5b7493856708b0ab66814ef98a8f151efc2d9245ca10286860f9d21f5e`

权威文件：

- `digit8x8_fixture.json`
- `digit8x8_manifest.json`
- `digit8x8.py`
- `generate_digit8x8_fixture.py`
- `test_digit8x8.py`

## 编码合同

1. 像素按亮度降序排列。
2. 同亮度按像素编号升序排列。
3. 前 16 个像素各发一个脉冲。
4. 编码函数只接收像素，不接收标签，不读取全局随机状态。
5. 每个像素最多出现一次。
6. 16 个 tick 的 patch mask 可以无损还原为扁平像素事件。

## 已通过测试

`python -m unittest -v test_digit8x8.py`：6/6 通过，覆盖：

- 固定尺寸、十分类、split 不交叠；
- 编码确定性与恒定事件数；
- 同亮度 tie-break；
- patch mask 往返还原；
- 标签/全局随机状态不影响编码；
- manifest 与 fixture SHA-256 绑定。

## 下一阶段边界

D1 才开始无学习基线和软件可分性测试。D0 不包含：

- ENeuron 网络训练；
- RTL 图像 wrapper；
- Vivado 30 核实现；
- 任何准确率结论；
- 对 16×16 或 28×28 的容量外推。

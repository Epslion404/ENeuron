# B2 packet-NPU 顶层时序失败证据

- 构建提交：`1bfeb1289bf251f2f4c7c20e4b6e0b225fcdc846`
- 器件：`xc7z020clg484-2`
- Vivado：2024.1
- 时钟：NPU `200 MHz`
- route：完成，routing errors `0`
- DRC：hard errors `0`
- bitstream/XSA：已生成，但不得作为物理签核或正式上板输入
- setup：`WNS=-2.750 ns`、`TNS=-8221.926 ns`、8788 个失败端点
- hold：`WHS=+0.053 ns`、`THS=0`

相对前一版 `f4827e2` 的 `WNS=-2.777 ns`、`TNS=-9315.718 ns`，命令 FIFO 保持槽切片带来小幅改善，并且最差路径已不再是 `command_fifo -> model_staging`。当前最差路径为 `egress/response_mem` BRAM 输出到 `egress/crc_state`，数据路径约 `7.640 ns`、8 级逻辑。

该目录只记录失败边界和诊断输入；它不表示 B2-GATE、packet path 实板验证或 ENeuron 动态剪枝性能/功耗目标已完成。

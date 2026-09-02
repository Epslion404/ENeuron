# N1 Dense INT8 NPU 软件基线报告

日期：2026-09-02
状态：`SOFTWARE_PASS / RTL_NOT_STARTED`

## 1. 范围

本阶段只建立传统 NPU 的 Python 黄金模型，不接入神经元、不实现剪枝、不运行 Vivado。模型固定为 `64 -> 32 -> 10` 两层 MLP，用于为后续 N2 软件门控和 N3 RTL 门控提供共同参考。

## 2. 已实现行为

- 权重和激活使用 signed INT8。
- 偏置和累加器使用 signed INT24。
- 每次乘积加入后立即饱和，禁止回绕。
- 隐藏层执行 ReLU，再饱和到 INT8。
- 输出层保留 INT24 logits。
- 类别解码使用确定性 argmax；并列时选择较小类别编号。
- 可选 `abstain_margin`，触发时输出全零 one-hot。
- 每四条输入连接作为一个执行组；每组 dense 权重占两个逻辑字并发出四次乘加。
- lane 数固定扫描 `1/2/4/8`，只改变组批次周期，不改变数值结果和读取总量。

## 3. 软件账本基线

| lane | 总周期 | 逻辑权重读取 | 乘加发射 |
|---:|---:|---:|---:|
| 1 | 592 | 1184 | 2368 |
| 2 | 296 | 1184 | 2368 |
| 4 | 148 | 1184 | 2368 |
| 8 | 74 | 1184 | 2368 |

周期只包含逻辑组执行，不包含 DMA、启动、排空、跨时钟域、背压和网口开销。逻辑读取不等于物理 BRAM 端口访问，必须在 RTL/Vivado 阶段重新测量。

## 4. 验证结果

```powershell
python -X utf8 -m unittest -v test_npu_dense_reference.py
python -m py_compile npu_dense_reference.py test_npu_dense_reference.py
git diff --check
```

结果：9/9 单元测试通过，Python 编译通过，差异检查通过。覆盖随机 signed 向量、INT24 边界饱和、ReLU、确定性 argmax、abstain、四种 lane、数值等价和无神经元十分类 codebook smoke task。

## 5. 结论与边界

N1 的 Python 数据平面和工作量合同已建立，可作为 N2/N3 的黄金参考。十分类 codebook 只证明数据路径能完成一个固定可分任务，不等于 8×8 图像识别，也不等于训练已经在 NPU 内完成。RTL、逐 tick 协同仿真、资源、时序和板级吞吐仍未证明。

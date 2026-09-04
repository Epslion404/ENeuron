# OF4d：模型顺序装载与原子提交合同

状态：设计审核稿，尚未进入 RTL。

## 合同

- 复位后 `model_valid=0`，模型配置口处于 `EMPTY`，写索引为 0。
- 仅接受固定顺序的 634 个 32-bit word：512 个第一层权重、32 个第一层 bias、80 个第二层权重、10 个第二层 bias。
- 配置数据采用 `cfg_valid/cfg_ready`；每次握手只消费当前索引。非法 word 仍握手并返回一个错误响应，索引和已写内容保持不变，可在相同索引重试。
- bias 在写入前执行冻结的安全范围检查；权重 word 按低字节优先解释为四个 signed INT8。
- 第 634 个合法 word 写入后进入 `COMPLETE`，但模型仍不可见；只有 `MODEL_COMMIT` 在完全 idle、无结果背压且未冻结时才把模型原子发布为可推理。
- `MODEL_COMMIT` 失败不得改变 `model_valid`、写索引或任何已提交参数。
- 提交后配置口锁定；只有 hard reset 才能重新装载。`STATE_CLEAR`、mask 操作和样本推理不得隐式改变模型版本。
- 响应槽单深度。`rsp_ready=0` 时响应 payload、错误码和所有配置状态必须稳定，且 `cfg_ready=0`。

## 禁止推断

本合同不证明 BRAM 推断、LUT/FF/DSP 数量、时序、吞吐、功耗或分类准确率；这些属于后续 RTL/OOC 与系统验证阶段。

## RTL 前置测试

必须先完成 634-word 全长轨迹、非法 bias 同索引重试、最后一字失败零副作用、commit 前后 model_valid、commit 与样本/结果背压冲突、重复 commit 和 reset 后旧 RAM 不可推理等 Python 周期测试。

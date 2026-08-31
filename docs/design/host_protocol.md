# 片外 Host 与数字神经网络训练协议

## 片上职责

片上只做确定性的数字事件计算：

- 接收 `event(valid, synapse_id, step_id)`；
- 更新膜电位、电流、不应期、pre/post trace 和 eligibility；
- 产生输出 spike；
- 接收 signed `modulator` 并提交权重更新；
- 在 `INFER` 模式冻结权重。

片上不实现标签解析、损失函数、奖励计算或数据集管理。

## 片外职责

Host 负责：

1. 把传感器或数据编码成输入事件；
2. 按 episode 顺序发送事件；
3. 收集输出 spike 或 spike count；
4. 根据标签、奖励或预测误差生成 signed modulator；
5. 把每个神经元的 modulator 写回片上；
6. 保存和加载权重。

## 一次训练 episode

```text
HOST -> TILE: EPISODE_START(episode_id)
HOST -> TILE: event(episode_id, synapse_id, step_id)
TILE -> HOST: spike(episode_id, neuron_id, step_id)
TILE -> HOST: EPISODE_END(episode_id, output_summary)
TILE: snapshot eligibility -> pending buffer(commit_id)
HOST -> TILE: MODULATOR(commit_id, layer_id, neuron_id, signed_value)
HOST -> TILE: MOD_COMMIT(commit_id)
TILE: eligibility_snapshot * modulator -> saturating weight commit
TILE -> HOST: COMMIT_DONE(commit_id) + status counters
```

`commit_id` 必须单调且不可重复。主机通过 USB、PCIe 或 MMIO 的传输延迟不能改变权重更新结果；过期、重复或未知的 `commit_id` 必须被拒绝。

隐藏层到输出层使用固定 1 tick 的 pending FIFO，避免组合跨层路径。片上每个时间步应具有明确的 `TICK_BEGIN -> INPUT_EVENT* -> TICK_COMMIT` 边界，保证所有同 tick 输入先完成再做一次阈值判断。

## 推理 episode

```text
HOST -> TILE: INFER_ENABLE
HOST -> TILE: event stream
TILE -> HOST: output spike stream
HOST: spike count / first-spike decoder
```

推理期间所有突触 RAM 的写使能必须关闭。

## 当前 Python 对应

- `DigitalSNN2Layer` 对应片上两层事件网络；
- `HostTrainingController` 对应片外目标/调制生成器；
- `artifacts/results/network_results.json` 对应一次训练与推理验收记录。

## 两种调制协议

### 可寻址目标调制

主机根据标签向目标神经元发送 `+1`，向非目标神经元发送 `-1`。这是当前两层 MVP 的稳定协议，隐藏层也可以按分组接收不同调制。

### 奖励调制

主机根据输出动作和环境反馈生成 signed reward。reward 只写给本 episode 实际选择的输出动作神经元，未参与动作的输出神经元写 `0`。

当前验证表明，即使加入逐 tick WTA，把同一个 reward 广播给隐藏层仍会产生信用分配失败。因此推荐使用两阶段协议：

```text
阶段 1：Host 目标调制 -> 训练隐藏特征，输出层冻结
阶段 2：隐藏层冻结 -> Host epsilon 探索 + reward 训练输出层
阶段 3：INFER，关闭所有 weight RAM 写使能
```

阶段切换只改变 RAM 写使能和 modulator 路由，不要求片上实现损失函数或反向传播。

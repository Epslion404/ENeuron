"""ENeuron 单核局部剪枝 wrapper 的定向 Python/Icarus 测试。"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from rtl_multicycle_cosim import find_tool


ROOT = Path(__file__).resolve().parent


def _testbench() -> str:
    return r"""
module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;

  logic rst;
  logic [1:0] mode_state;
  logic state_clear, tick_valid, snapshot_we, mod_valid, weight_we;
  logic [3:0] input_spikes;
  logic [15:0] snapshot_commit_id, mod_commit_id;
  logic signed [1:0] modulator;
  logic [1:0] weight_addr;
  logic signed [7:0] weight_wdata;
  logic signed [7:0] weight_rdata;
  logic ready, busy, done, protocol_error, spike;
  logic signed [15:0] membrane;
  logic [7:0] threshold_state;
  logic snapshot_valid_state;
  logic [47:0] eligibility_snapshot_flat_state;
  logic pending_snapshot_valid_state;
  logic [15:0] pending_snapshot_id_state;

  logic prune_cmd_valid, prune_cmd_ready, prune_rsp_valid, prune_rsp_ready;
  logic [2:0] prune_cmd_opcode, prune_rsp_status;
  logic [15:0] prune_cmd_id, prune_rsp_id;
  logic [3:0] prune_rsp_mask;
  logic cfg_mask_valid, cfg_mask_ready, cfg_mask_done, cfg_mask_error;
  logic [3:0] cfg_mask_data;
  logic [3:0] issue_mask;
  logic [15:0] utility_flat;
  logic [3:0] structural_mask_state;
  logic mask_valid_state;
  logic last_observation_valid_state;
  logic [15:0] last_observation_id_state;

  logic bare_state_clear, bare_tick_valid, bare_snapshot_we, bare_mod_valid;
  logic [3:0] bare_input_spikes;
  logic bare_learn_enable;
  logic signed [1:0] bare_modulator;
  logic bare_weight_we;
  logic signed [7:0] bare_weight_rdata;
  logic bare_ready, bare_done, bare_spike;
  logic signed [15:0] bare_membrane;
  logic [7:0] bare_threshold_state;
  logic bare_snapshot_valid_state;
  logic [47:0] bare_snapshot_flat;
  logic saved_bare_spike;

  eneuron_local_prune_wrapper dut (
    .clk(clk), .rst(rst), .mode_state(mode_state),
    .state_clear(state_clear), .tick_valid(tick_valid), .input_spikes(input_spikes),
    .snapshot_we(snapshot_we), .snapshot_commit_id(snapshot_commit_id),
    .mod_valid(mod_valid), .mod_commit_id(mod_commit_id), .modulator(modulator),
    .weight_we(weight_we), .weight_addr(weight_addr), .weight_wdata(weight_wdata),
    .weight_rdata(weight_rdata), .ready(ready), .busy(busy), .done(done),
    .protocol_error(protocol_error), .spike(spike), .membrane(membrane),
    .threshold_state(threshold_state), .snapshot_valid_state(snapshot_valid_state),
    .eligibility_snapshot_flat_state(eligibility_snapshot_flat_state),
    .pending_snapshot_valid_state(pending_snapshot_valid_state),
    .pending_snapshot_id_state(pending_snapshot_id_state),
    .prune_cmd_valid(prune_cmd_valid), .prune_cmd_ready(prune_cmd_ready),
    .prune_cmd_opcode(prune_cmd_opcode), .prune_cmd_id(prune_cmd_id),
    .prune_rsp_valid(prune_rsp_valid), .prune_rsp_ready(prune_rsp_ready),
    .prune_rsp_status(prune_rsp_status), .prune_rsp_id(prune_rsp_id),
    .prune_rsp_mask(prune_rsp_mask),
    .cfg_mask_valid(cfg_mask_valid), .cfg_mask_ready(cfg_mask_ready),
    .cfg_mask_data(cfg_mask_data), .cfg_mask_done(cfg_mask_done),
    .cfg_mask_error(cfg_mask_error), .issue_mask(issue_mask),
    .utility_flat(utility_flat), .structural_mask_state(structural_mask_state),
    .mask_valid_state(mask_valid_state),
    .last_observation_valid_state(last_observation_valid_state),
    .last_observation_id_state(last_observation_id_state)
  );

  digital_lif_engine bare (
    .clk(clk), .rst(rst), .state_clear(bare_state_clear),
    .tick_valid(bare_tick_valid), .input_spikes(bare_input_spikes),
    .learn_enable(bare_learn_enable), .snapshot_we(bare_snapshot_we),
    .mod_valid(bare_mod_valid), .modulator(bare_modulator),
    .weight_we(bare_weight_we), .weight_addr(weight_addr),
    .weight_wdata(weight_wdata), .weight_rdata(bare_weight_rdata),
    .ready(bare_ready), .done(bare_done), .spike(bare_spike),
    .membrane(bare_membrane), .threshold_state(bare_threshold_state),
    .snapshot_valid_state(bare_snapshot_valid_state),
    .eligibility_snapshot_flat_state(bare_snapshot_flat)
  );

  task clear_commands;
    begin
      state_clear=0; tick_valid=0; input_spikes=0; snapshot_we=0; snapshot_commit_id=0;
      mod_valid=0; mod_commit_id=0; modulator=0; weight_we=0; weight_addr=0; weight_wdata=0;
      prune_cmd_valid=0; prune_cmd_opcode=0; prune_cmd_id=0; prune_rsp_ready=1;
      cfg_mask_valid=0; cfg_mask_data=0;
      bare_state_clear=0; bare_tick_valid=0; bare_input_spikes=0; bare_learn_enable=1;
      bare_snapshot_we=0; bare_mod_valid=0; bare_modulator=0; bare_weight_we=0;
    end
  endtask

  task wait_wrapper_done;
    integer timeout;
    begin
      timeout = 0;
      saved_bare_spike = 1'b0;
      while (!done) begin
        @(posedge clk); #1; timeout=timeout+1;
        if (bare_done) saved_bare_spike = bare_spike;
        if (timeout > 40) $fatal(1, "wrapper command timeout");
      end
    end
  endtask

  task compare_public_core;
    integer address;
    begin
      if (spike!==saved_bare_spike || membrane!==bare_membrane ||
          threshold_state!==bare_threshold_state ||
          snapshot_valid_state!==bare_snapshot_valid_state ||
          eligibility_snapshot_flat_state!==bare_snapshot_flat)
        $fatal(1, "wrapper bypass core state mismatch");
      for (address=0; address<4; address=address+1) begin
        weight_addr=address[1:0]; #1;
        if (weight_rdata!==bare_weight_rdata)
          $fatal(1, "wrapper bypass weight mismatch at %0d", address);
      end
    end
  endtask

  task run_tick_pair(input logic [3:0] external_mask, input logic [3:0] bare_mask);
    begin
      @(negedge clk); clear_commands();
      tick_valid=1; input_spikes=external_mask;
      bare_tick_valid=1; bare_input_spikes=bare_mask;
      @(posedge clk); #1; clear_commands();
      wait_wrapper_done(); compare_public_core();
      @(posedge clk); #1;
    end
  endtask

  task run_snapshot_pair(input logic [15:0] commit_id);
    begin
      @(negedge clk); clear_commands();
      snapshot_we=1; snapshot_commit_id=commit_id; bare_snapshot_we=1;
      @(posedge clk); #1; clear_commands();
      wait_wrapper_done(); compare_public_core();
      if (!pending_snapshot_valid_state || pending_snapshot_id_state!==commit_id)
        $fatal(1, "wrapper pending snapshot metadata mismatch");
      @(posedge clk); #1;
    end
  endtask

  task run_mod_pair(input logic [15:0] commit_id, input logic signed [1:0] value);
    begin
      @(negedge clk); clear_commands();
      mod_valid=1; mod_commit_id=commit_id; modulator=value;
      bare_mod_valid=1; bare_modulator=value;
      @(posedge clk); #1; clear_commands();
      wait_wrapper_done(); compare_public_core();
      @(posedge clk); #1;
    end
  endtask

  task run_prune_commit_and_model_automatic_clear(input logic [15:0] commit_id);
    integer timeout;
    begin
      @(negedge clk); clear_commands();
      prune_cmd_valid=1; prune_cmd_opcode=3'd2; prune_cmd_id=commit_id;
      #1;
      if (!prune_cmd_ready) $fatal(1, "prune commit was not accepted");
      @(posedge clk); #1; clear_commands();
      timeout=0;
      while (!prune_rsp_valid) begin
        @(posedge clk); #1; timeout=timeout+1;
        if (timeout>20) $fatal(1, "prune commit response timeout");
      end
      if (prune_rsp_status!==0 || prune_rsp_mask!==4'b0011)
        $fatal(1, "prune commit response mismatch");

      // wrapper 的成功响应蕴含内部 STATE_CLEAR 已完成；裸核心同步执行一次作为黄金对照。
      @(negedge clk); clear_commands(); bare_state_clear=1;
      @(posedge clk); #1; clear_commands();
      while (!bare_done) begin @(posedge clk); #1; end
      @(posedge clk); #1;
    end
  endtask

  task hold_prune_response_and_reject_mod(input logic [15:0] commit_id);
    integer timeout;
    logic [15:0] saved_utility;
    begin
      saved_utility=utility_flat;
      @(negedge clk); clear_commands(); prune_rsp_ready=0;
      prune_cmd_valid=1; prune_cmd_opcode=3'd3; prune_cmd_id=16'd12;
      #1;
      if (!prune_cmd_ready) $fatal(1, "MASK_READ was not accepted");
      @(posedge clk); #1;
      prune_cmd_valid=0;
      timeout=0;
      while (!prune_rsp_valid) begin
        @(posedge clk); #1; timeout=timeout+1;
        if (timeout>8) $fatal(1, "MASK_READ response timeout");
      end

      // 未消费的 gate response 必须反压整个 wrapper，不能让核心单独接受 MOD。
      @(negedge clk); mod_valid=1; mod_commit_id=commit_id; modulator=2'b01; #1;
      if (ready) $fatal(1, "runtime ready escaped held prune response");
      @(posedge clk); #1;
      mod_valid=0; modulator=0;
      if (done || protocol_error || utility_flat!==saved_utility ||
          !pending_snapshot_valid_state || pending_snapshot_id_state!==commit_id)
        $fatal(1, "backpressured MOD changed architectural state");

      @(negedge clk); prune_rsp_ready=1;
      @(posedge clk); #1;
      clear_commands();
      @(posedge clk); #1;
    end
  endtask

  task reject_mod_without_observe(
    input logic [1:0] requested_mode,
    input logic [15:0] commit_id
  );
    logic [15:0] saved_utility;
    logic [47:0] saved_snapshot;
    begin
      saved_utility=utility_flat;
      saved_snapshot=eligibility_snapshot_flat_state;
      mode_state=requested_mode;
      @(negedge clk); clear_commands();
      mod_valid=1; mod_commit_id=commit_id; modulator=2'b01;
      @(posedge clk); #1; clear_commands();
      if (!done || !protocol_error || utility_flat!==saved_utility ||
          eligibility_snapshot_flat_state!==saved_snapshot ||
          !pending_snapshot_valid_state)
        $fatal(1, "illegal MOD was not atomic/non-mutating");
      @(posedge clk); #1;
    end
  endtask

  initial begin
    clear_commands(); mode_state=2'd1; rst=1;
    repeat(2) @(posedge clk); #1; rst=0;
    if (mask_valid_state || structural_mask_state!==4'b1111)
      $fatal(1, "dense bypass reset mismatch");

    // mask_valid=0 时，wrapper 与裸核心逐事务等价。
    run_tick_pair(4'b0001, 4'b0001);
    run_tick_pair(4'b0010, 4'b0010);
    run_tick_pair(4'b0100, 4'b0100);
    run_snapshot_pair(16'd7);

    // snapshot 后推进 live eligibility；MOD 与 OBSERVE 仍必须使用 committed snapshot。
    run_tick_pair(4'b1000, 4'b1000);
    run_mod_pair(16'd7, 2'b01);
    if (utility_flat!==16'h0222 || !last_observation_valid_state ||
        last_observation_id_state!==16'd7)
      $fatal(1, "MOD/OBSERVE evidence mismatch");
    if (pending_snapshot_valid_state)
      $fatal(1, "nonzero MOD did not consume pending snapshot");

    // 成功 commit 必须先自动清动态历史，再公开 0011 mask。
    run_prune_commit_and_model_automatic_clear(16'd9);
    run_snapshot_pair(16'd10);
    if (eligibility_snapshot_flat_state!==0)
      $fatal(1, "prune commit response escaped before automatic state clear");

    hold_prune_response_and_reject_mod(16'd10);
    reject_mod_without_observe(2'd1, 16'd11);
    reject_mod_without_observe(2'd2, 16'd10);
    mode_state=2'd1;

    // 零 MOD 走核心既有 no-op，消费 wrapper pending，但不得新增 OBSERVE。
    run_mod_pair(16'd10, 2'b00);
    if (utility_flat!==16'h0222 || last_observation_id_state!==16'd7 ||
        pending_snapshot_valid_state)
      $fatal(1, "zero MOD observation/pending contract mismatch");

    // committed mask 必须在核心 TICK 之前生效；输入 2 被 0011 屏蔽。
    input_spikes=4'b0100; #1;
    if (issue_mask!==0) $fatal(1, "issue mask not applied before core");
    run_tick_pair(4'b0100, 4'b0000);

    $display("ENEURON_LOCAL_PRUNE_WRAPPER_PASS");
    $finish;
  end
endmodule
"""


def run_wrapper_contract() -> None:
    """运行单核 wrapper 的旁路、观察和输入门控合同。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if not iverilog or not vvp:
        raise unittest.SkipTest("Icarus Verilog 未安装")

    sources = (
        ROOT / "digital_lif_engine.sv",
        ROOT / "local_prune_gate_2of4.sv",
        ROOT / "eneuron_local_prune_wrapper.sv",
    )
    with tempfile.TemporaryDirectory(prefix="eneuron_prune_wrapper_") as temp_dir:
        work = Path(temp_dir)
        testbench = work / "tb.sv"
        executable = work / "sim.out"
        testbench.write_text(_testbench(), encoding="utf-8")
        compile_result = subprocess.run(
            [str(iverilog), "-g2012", "-o", str(executable), str(testbench), *(str(source) for source in sources)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if compile_result.returncode:
            raise AssertionError(
                f"wrapper RTL 编译失败:\n{compile_result.stdout}\n{compile_result.stderr}"
            )
        result = subprocess.run(
            [str(vvp), str(executable)], cwd=ROOT, capture_output=True, text=True
        )
        if result.returncode or "ENEURON_LOCAL_PRUNE_WRAPPER_PASS" not in result.stdout:
            raise AssertionError(
                f"wrapper RTL 合同失败:\n{result.stdout}\n{result.stderr}"
            )


def _network_managed_clear_testbench() -> str:
    return r"""
module tb;
  logic clk=0; always #5 clk=~clk;
  logic rst; logic [1:0] mode_state;
  logic state_clear,tick_valid,snapshot_we,mod_valid,weight_we;
  logic [3:0] input_spikes; logic [15:0] snapshot_commit_id,mod_commit_id;
  logic signed [1:0] modulator; logic [1:0] weight_addr; logic signed [7:0] weight_wdata,weight_rdata;
  logic ready,busy,done,protocol_error,spike; logic signed [15:0] membrane; logic [7:0] threshold_state;
  logic snapshot_valid_state; logic [47:0] eligibility_snapshot_flat_state;
  logic pending_snapshot_valid_state; logic [15:0] pending_snapshot_id_state;
  logic prune_cmd_valid,prune_cmd_ready,prune_rsp_valid,prune_rsp_ready;
  logic [2:0] prune_cmd_opcode,prune_rsp_status; logic [15:0] prune_cmd_id,prune_rsp_id;
  logic [3:0] prune_rsp_mask; logic cfg_mask_valid,cfg_mask_ready,cfg_mask_done,cfg_mask_error;
  logic [3:0] cfg_mask_data,issue_mask,structural_mask_state; logic [15:0] utility_flat;
  logic mask_valid_state,last_observation_valid_state; logic [15:0] last_observation_id_state;
  logic [31:0] hidden_dense_reads_state,hidden_reads_issued_state,hidden_reads_saved_state;
  logic [31:0] output_dense_reads_state,output_reads_issued_state,output_reads_saved_state;

  eneuron_local_prune_wrapper #(.AUTO_CLEAR_ON_COMMIT(1'b0)) dut (.*);

  task clear_commands; begin
    state_clear=0; tick_valid=0; input_spikes=0; snapshot_we=0; snapshot_commit_id=0;
    mod_valid=0; mod_commit_id=0; modulator=0; weight_we=0; weight_addr=0; weight_wdata=0;
    prune_cmd_valid=0; prune_cmd_opcode=0; prune_cmd_id=0; prune_rsp_ready=1;
    cfg_mask_valid=0; cfg_mask_data=0;
  end endtask

  task wait_done; integer timeout; begin
    timeout=0;
    while(!done) begin @(posedge clk); #1; timeout=timeout+1;
      if(timeout>40) $fatal(1,"runtime timeout");
    end
  end endtask

  initial begin
    clear_commands(); mode_state=2'd1; rst=1; repeat(2) @(posedge clk); #1; rst=0;

    @(negedge clk); tick_valid=1; input_spikes=4'b0001;
    @(posedge clk); #1; clear_commands(); wait_done();
    if(membrane==0) $fatal(1,"directed setup did not create dynamic state");
    @(posedge clk); #1;

    @(negedge clk); prune_cmd_valid=1; prune_cmd_opcode=3'd2; prune_cmd_id=16'd3; #1;
    if(!prune_cmd_ready) $fatal(1,"network-managed commit not ready");
    @(posedge clk); #1; clear_commands();
    while(!prune_rsp_valid) begin @(posedge clk); #1; end
    if(prune_rsp_status!=0 || prune_rsp_mask!=4'b0011)
      $fatal(1,"network-managed commit response mismatch");
    if(membrane==0)
      $fatal(1,"AUTO_CLEAR_ON_COMMIT=0 cleared state before network barrier");
    @(posedge clk); #1;

    // 网络 barrier 随后广播普通 STATE_CLEAR。
    @(negedge clk); clear_commands(); state_clear=1;
    @(posedge clk); #1; clear_commands(); wait_done();
    if(membrane!=0 || !mask_valid_state || structural_mask_state!=4'b0011)
      $fatal(1,"network-managed STATE_CLEAR contract mismatch");

    $display("ENEURON_NETWORK_MANAGED_CLEAR_PASS");
    $finish;
  end
endmodule
"""


def run_network_managed_clear_contract() -> None:
    """验证参数 0 把清历史责任交给网络级 barrier。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if not iverilog or not vvp:
        raise unittest.SkipTest("Icarus Verilog 未安装")
    with tempfile.TemporaryDirectory(prefix="eneuron_network_clear_") as temp_dir:
        work = Path(temp_dir)
        testbench = work / "tb.sv"
        executable = work / "sim.out"
        testbench.write_text(_network_managed_clear_testbench(), encoding="utf-8")
        sources = (
            ROOT / "digital_lif_engine.sv",
            ROOT / "local_prune_gate_2of4.sv",
            ROOT / "eneuron_local_prune_wrapper.sv",
        )
        compile_result = subprocess.run(
            [str(iverilog), "-g2012", "-o", str(executable), str(testbench), *(str(source) for source in sources)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if compile_result.returncode:
            raise AssertionError(
                f"network-managed wrapper 编译失败:\n{compile_result.stdout}\n{compile_result.stderr}"
            )
        result = subprocess.run(
            [str(vvp), str(executable)], cwd=ROOT, capture_output=True, text=True
        )
        if result.returncode or "ENEURON_NETWORK_MANAGED_CLEAR_PASS" not in result.stdout:
            raise AssertionError(
                f"network-managed clear 合同失败:\n{result.stdout}\n{result.stderr}"
            )


__all__ = ["run_network_managed_clear_contract", "run_wrapper_contract"]

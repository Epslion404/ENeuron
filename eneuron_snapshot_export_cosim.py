"""ENeuron committed eligibility snapshot 公开端口定向协同仿真。"""

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
  localparam integer N_INPUTS = 4;
  localparam integer ELIG_BITS = 12;

  logic clk = 1'b0;
  always #5 clk = ~clk;

  logic rst;
  logic state_clear;
  logic tick_valid;
  logic [N_INPUTS-1:0] input_spikes;
  logic learn_enable;
  logic snapshot_we;
  logic mod_valid;
  logic signed [1:0] modulator;
  logic weight_we;
  logic [1:0] weight_addr;
  logic signed [7:0] weight_wdata;
  logic signed [7:0] weight_rdata;
  logic ready;
  logic done;
  logic spike;
  logic signed [15:0] membrane;
  logic [7:0] threshold_state;
  logic snapshot_valid_state;
  logic [N_INPUTS*ELIG_BITS-1:0] eligibility_snapshot_flat_state;

  digital_lif_engine #(.N_INPUTS(N_INPUTS)) dut (
    .clk(clk),
    .rst(rst),
    .state_clear(state_clear),
    .tick_valid(tick_valid),
    .input_spikes(input_spikes),
    .learn_enable(learn_enable),
    .snapshot_we(snapshot_we),
    .mod_valid(mod_valid),
    .modulator(modulator),
    .weight_we(weight_we),
    .weight_addr(weight_addr),
    .weight_wdata(weight_wdata),
    .weight_rdata(weight_rdata),
    .ready(ready),
    .done(done),
    .spike(spike),
    .membrane(membrane),
    .threshold_state(threshold_state),
    .snapshot_valid_state(snapshot_valid_state),
    .eligibility_snapshot_flat_state(eligibility_snapshot_flat_state)
  );

  task clear_commands;
    begin
      state_clear = 1'b0;
      tick_valid = 1'b0;
      input_spikes = '0;
      learn_enable = 1'b1;
      snapshot_we = 1'b0;
      mod_valid = 1'b0;
      modulator = '0;
      weight_we = 1'b0;
      weight_addr = '0;
      weight_wdata = '0;
    end
  endtask

  task run_tick(input logic [3:0] mask);
    begin
      @(negedge clk);
      clear_commands();
      input_spikes = mask;
      tick_valid = 1'b1;
      @(posedge clk);
      #1;
      clear_commands();
      while (!done) begin
        @(posedge clk);
        #1;
      end
    end
  endtask

  task expect_snapshot(
    input logic expected_valid,
    input integer lane0,
    input integer lane1,
    input integer lane2,
    input integer lane3
  );
    begin
      if (snapshot_valid_state !== expected_valid)
        $fatal(1, "snapshot valid mismatch");
      if ($signed(eligibility_snapshot_flat_state[0*ELIG_BITS +: ELIG_BITS]) !== lane0 ||
          $signed(eligibility_snapshot_flat_state[1*ELIG_BITS +: ELIG_BITS]) !== lane1 ||
          $signed(eligibility_snapshot_flat_state[2*ELIG_BITS +: ELIG_BITS]) !== lane2 ||
          $signed(eligibility_snapshot_flat_state[3*ELIG_BITS +: ELIG_BITS]) !== lane3)
        $fatal(1, "snapshot lane order/value mismatch");
    end
  endtask

  integer cycle;
  initial begin
    clear_commands();
    rst = 1'b1;
    repeat (2) @(posedge clk);
    #1;
    rst = 1'b0;
    expect_snapshot(1'b0, 0, 0, 0, 0);

    // 只通过公开 TICK 接口产生四路不同的 live eligibility。
    run_tick(4'b0001);
    run_tick(4'b0010);
    run_tick(4'b0100);
    expect_snapshot(1'b0, 0, 0, 0, 0);

    // 接受 SNAPSHOT 后，四拍扫描期间必须继续导出旧 committed 值。
    @(negedge clk);
    clear_commands();
    snapshot_we = 1'b1;
    @(posedge clk);
    #1;
    clear_commands();
    for (cycle = 0; cycle < N_INPUTS; cycle = cycle + 1) begin
      expect_snapshot(1'b0, 0, 0, 0, 0);
      if (done) $fatal(1, "snapshot completed before commit cycle");
      @(posedge clk);
      #1;
    end

    // commit 沿同时发布完整数据、valid 和 done。
    @(posedge clk);
    #1;
    expect_snapshot(1'b1, 19, 24, 32, 0);
    if (!done || !ready) $fatal(1, "snapshot commit handshake mismatch");

    // STATE_CLEAR 保留 committed snapshot。
    @(negedge clk);
    clear_commands();
    state_clear = 1'b1;
    @(posedge clk);
    #1;
    clear_commands();
    if (!done) $fatal(1, "state clear did not complete");
    expect_snapshot(1'b1, 19, 24, 32, 0);

    // 同步硬复位才清 valid 和数据。
    @(negedge clk);
    rst = 1'b1;
    @(posedge clk);
    #1;
    rst = 1'b0;
    expect_snapshot(1'b0, 0, 0, 0, 0);

    $display("ENEURON_SNAPSHOT_EXPORT_PASS");
    $finish;
  end
endmodule
"""


def run_snapshot_export_contract() -> None:
    """编译并验证 committed snapshot 公开端口合同。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if not iverilog or not vvp:
        raise unittest.SkipTest("Icarus Verilog 未安装")

    with tempfile.TemporaryDirectory(prefix="eneuron_snapshot_export_") as temp_dir:
        work = Path(temp_dir)
        testbench = work / "tb.sv"
        executable = work / "sim.out"
        testbench.write_text(_testbench(), encoding="utf-8")
        subprocess.run(
            [str(iverilog), "-g2012", "-o", str(executable), str(testbench), str(ROOT / "digital_lif_engine.sv")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            [str(vvp), str(executable)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        if "ENEURON_SNAPSHOT_EXPORT_PASS" not in result.stdout:
            raise AssertionError(f"snapshot export PASS 标记缺失:\n{result.stdout}\n{result.stderr}")


__all__ = ["run_snapshot_export_contract"]

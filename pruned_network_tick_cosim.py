"""固定 4→8→2 网络 TICK 调度器的 Icarus 定向验证。"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from rtl_tile_cosim import find_tool


ROOT = Path(__file__).resolve().parent


def _run(source: str) -> str:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("Icarus Verilog 工具不可用")
    with tempfile.TemporaryDirectory(prefix="np4b_tick_") as temp_dir:
        temp = Path(temp_dir)
        tb = temp / "tb.sv"
        sim = temp / "sim.out"
        tb.write_text(source, encoding="utf-8")
        compiled = subprocess.run(
            [
                os.fspath(iverilog),
                "-g2012",
                "-s",
                "tb",
                "-o",
                os.fspath(sim),
                os.fspath(ROOT / "pruned_network_tick_scheduler.sv"),
                os.fspath(tb),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if compiled.returncode != 0:
            raise AssertionError("tick scheduler 编译失败:\n" + compiled.stdout + compiled.stderr)
        ran = subprocess.run(
            [os.fspath(vvp), os.fspath(sim)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if ran.returncode != 0:
            raise AssertionError("tick scheduler 仿真失败:\n" + ran.stdout + ran.stderr)
        return ran.stdout


def run_one_tick_route_contract() -> None:
    """两次 TICK 证明输出只消费前一拍 pending detector 向量。"""

    output = _run(
        r"""
module tb;
  logic clk = 1'b0; always #5 clk = ~clk;
  logic rst;
  logic tick_valid, tick_ready, flush_valid, flush_ready, rsp_valid, rsp_ready;
  logic [3:0] input_spikes;
  logic [7:0] hidden_train_post;
  logic [1:0] output_train_post;
  logic [2:0] rsp_status;
  logic [7:0] hidden_spikes, pending_hidden_state;
  logic [1:0] output_spikes;
  logic [7:0] hidden_cmd_valid, hidden_cmd_ready;
  logic [31:0] hidden_input_spikes_flat;
  logic [7:0] hidden_train_post_out;
  logic [1:0] output_cmd_valid, output_cmd_ready;
  logic [7:0] output_input_spikes_flat;
  logic [1:0] output_train_post_out;
  logic [7:0] hidden_rsp_valid, hidden_rsp_ready, hidden_rsp_spike;
  logic [23:0] hidden_rsp_status_flat;
  logic [1:0] output_rsp_valid, output_rsp_ready, output_rsp_spike;
  logic [5:0] output_rsp_status_flat;
  logic busy, protocol_error;

  pruned_network_tick_scheduler dut(.*);

  task automatic start_tick(input logic [3:0] mask);
    begin
      input_spikes = mask;
      tick_valid = 1'b1;
      #1;
      if (!tick_ready || hidden_cmd_valid !== 8'hff || output_cmd_valid !== 2'b11)
        $fatal(1, "TICK_NOT_ATOMIC ready=%0d hidden=%h output=%h",
               tick_ready, hidden_cmd_valid, output_cmd_valid);
      if (hidden_input_spikes_flat !== {8{mask}})
        $fatal(1, "HIDDEN_INPUT_REPLICATION_WRONG value=%h", hidden_input_spikes_flat);
      @(posedge clk);
      #1 tick_valid = 1'b0;
    end
  endtask

  task automatic finish_tick(
      input logic [7:0] next_hidden,
      input logic [1:0] next_output
  );
    begin
      hidden_rsp_spike = next_hidden;
      output_rsp_spike = next_output;
      hidden_rsp_valid = 8'b00001111;
      output_rsp_valid = 2'b01;
      @(posedge clk);
      #1;
      hidden_rsp_valid = 8'b11110000;
      output_rsp_valid = 2'b10;
      @(posedge clk);
      #1;
      hidden_rsp_valid = '0;
      output_rsp_valid = '0;
      if (!rsp_valid || rsp_status != 0)
        $fatal(1, "TICK_RESPONSE_MISSING valid=%0d status=%0d", rsp_valid, rsp_status);
      if (hidden_spikes != next_hidden || output_spikes != next_output)
        $fatal(1, "TICK_SPIKES_WRONG hidden=%h output=%h", hidden_spikes, output_spikes);
      rsp_ready = 1'b1;
      @(posedge clk);
      #1 rsp_ready = 1'b0;
    end
  endtask

  initial begin
    rst = 1'b1;
    tick_valid = 1'b0;
    flush_valid = 1'b0;
    input_spikes = '0;
    hidden_train_post = '0;
    output_train_post = '0;
    rsp_ready = 1'b0;
    hidden_cmd_ready = 8'hff;
    output_cmd_ready = 2'b11;
    hidden_rsp_valid = '0;
    hidden_rsp_spike = '0;
    hidden_rsp_status_flat = '0;
    output_rsp_valid = '0;
    output_rsp_spike = '0;
    output_rsp_status_flat = '0;
    repeat (2) @(posedge clk);
    rst = 1'b0;

    start_tick(4'b0101);
    if (output_input_spikes_flat !== 8'h00)
      $fatal(1, "FIRST_TICK_COMBINATIONAL_PENETRATION output_input=%h",
             output_input_spikes_flat);
    finish_tick(8'ha5, 2'b00);
    if (pending_hidden_state != 8'ha5)
      $fatal(1, "PENDING_NOT_UPDATED value=%h", pending_hidden_state);

    start_tick(4'b1010);
    if (output_input_spikes_flat !== 8'ha5)
      $fatal(1, "SECOND_TICK_DID_NOT_USE_OLD_PENDING output_input=%h",
             output_input_spikes_flat);
    finish_tick(8'h3c, 2'b10);
    if (pending_hidden_state != 8'h3c)
      $fatal(1, "SECOND_PENDING_NOT_UPDATED value=%h", pending_hidden_state);

    $display("NP4B_TICK_ONE_ROUTE_DELAY_PASS");
    $finish;
  end
endmodule
"""
    )
    if "NP4B_TICK_ONE_ROUTE_DELAY_PASS" not in output:
        raise AssertionError("未看到一拍路由合同通过标记")


def run_route_flush_contract() -> None:
    """先建立 pending，再证明 flush 只启动两个输出并在完成后清 pending。"""

    output = _run(
        r"""
module tb;
  logic clk = 1'b0; always #5 clk = ~clk;
  logic rst;
  logic tick_valid, tick_ready, flush_valid, flush_ready, rsp_valid, rsp_ready;
  logic [3:0] input_spikes;
  logic [7:0] hidden_train_post;
  logic [1:0] output_train_post;
  logic [2:0] rsp_status;
  logic [7:0] hidden_spikes, pending_hidden_state;
  logic [1:0] output_spikes;
  logic [7:0] hidden_cmd_valid, hidden_cmd_ready;
  logic [31:0] hidden_input_spikes_flat;
  logic [7:0] hidden_train_post_out;
  logic [1:0] output_cmd_valid, output_cmd_ready;
  logic [7:0] output_input_spikes_flat;
  logic [1:0] output_train_post_out;
  logic [7:0] hidden_rsp_valid, hidden_rsp_ready, hidden_rsp_spike;
  logic [23:0] hidden_rsp_status_flat;
  logic [1:0] output_rsp_valid, output_rsp_ready, output_rsp_spike;
  logic [5:0] output_rsp_status_flat;
  logic busy, protocol_error;

  pruned_network_tick_scheduler dut(.*);

  initial begin
    rst = 1'b1;
    tick_valid = 1'b0;
    flush_valid = 1'b0;
    input_spikes = 4'b1111;
    hidden_train_post = '0;
    output_train_post = '0;
    rsp_ready = 1'b0;
    hidden_cmd_ready = 8'hff;
    output_cmd_ready = 2'b11;
    hidden_rsp_valid = '0;
    hidden_rsp_spike = 8'h96;
    hidden_rsp_status_flat = '0;
    output_rsp_valid = '0;
    output_rsp_spike = 2'b01;
    output_rsp_status_flat = '0;
    repeat (2) @(posedge clk);
    rst = 1'b0;

    tick_valid = 1'b1;
    @(posedge clk);
    #1 tick_valid = 1'b0;
    hidden_rsp_valid = 8'hff;
    output_rsp_valid = 2'b11;
    @(posedge clk);
    #1 hidden_rsp_valid = '0; output_rsp_valid = '0;
    if (!rsp_valid || pending_hidden_state != 8'h96)
      $fatal(1, "SETUP_TICK_FAILED pending=%h valid=%0d",
             pending_hidden_state, rsp_valid);
    rsp_ready = 1'b1;
    @(posedge clk);
    #1 rsp_ready = 1'b0;

    flush_valid = 1'b1;
    #1;
    if (!flush_ready || hidden_cmd_valid !== 8'h00 || output_cmd_valid !== 2'b11)
      $fatal(1, "FLUSH_LAUNCH_WRONG ready=%0d hidden=%h output=%h",
             flush_ready, hidden_cmd_valid, output_cmd_valid);
    if (output_input_spikes_flat !== 8'h96)
      $fatal(1, "FLUSH_INPUT_WRONG value=%h", output_input_spikes_flat);
    @(posedge clk);
    #1 flush_valid = 1'b0;

    // 隐藏响应即使噪声拉高也不得被 flush 消费。
    hidden_rsp_valid = 8'hff;
    hidden_rsp_spike = 8'hff;
    output_rsp_valid = 2'b11;
    output_rsp_spike = 2'b10;
    @(posedge clk);
    #1 hidden_rsp_valid = '0; output_rsp_valid = '0;
    if (hidden_rsp_ready !== 8'h00)
      $fatal(1, "FLUSH_CONSUMED_HIDDEN_RESPONSE ready=%h", hidden_rsp_ready);
    if (!rsp_valid || output_spikes != 2'b10 || hidden_spikes != 0)
      $fatal(1, "FLUSH_RESPONSE_WRONG valid=%0d hidden=%h output=%h",
             rsp_valid, hidden_spikes, output_spikes);
    if (pending_hidden_state != 0)
      $fatal(1, "FLUSH_DID_NOT_CLEAR_PENDING value=%h", pending_hidden_state);

    $display("NP4B_ROUTE_FLUSH_PASS");
    $finish;
  end
endmodule
"""
    )
    if "NP4B_ROUTE_FLUSH_PASS" not in output:
        raise AssertionError("未看到 route flush 合同通过标记")

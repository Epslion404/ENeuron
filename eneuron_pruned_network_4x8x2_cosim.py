"""ENeuron 4→8→2 剪枝网络的 Python/Icarus 定向验证。"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from rtl_multicycle_cosim import find_tool


ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("eneuron_pruned_network_4x8x2_cosim")


def _run_testbench(source: str) -> str:
    """编译并运行一个只观察网络公开接口的 testbench。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("Icarus Verilog 工具不可用")

    with tempfile.TemporaryDirectory(prefix="np4b_eneuron_network_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "sim.out"
        tb_path.write_text(source, encoding="utf-8")
        sources = [
            ROOT / "digital_lif_engine.sv",
            ROOT / "local_prune_gate_2of4.sv",
            ROOT / "eneuron_local_prune_wrapper.sv",
            ROOT / "pruned_network_tick_scheduler.sv",
            ROOT / "local_prune_commit_barrier.sv",
            ROOT / "eneuron_pruned_network_4x8x2.sv",
            tb_path,
        ]
        compiled = subprocess.run(
            [
                os.fspath(iverilog),
                "-g2012",
                "-s",
                "tb",
                "-o",
                os.fspath(sim_path),
                *(os.fspath(path) for path in sources),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if compiled.returncode != 0:
            raise AssertionError(
                "ENeuron 4→8→2 顶层编译失败:\n"
                + compiled.stdout
                + compiled.stderr
            )
        ran = subprocess.run(
            [os.fspath(vvp), os.fspath(sim_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if ran.returncode != 0:
            raise AssertionError(
                "ENeuron 4→8→2 顶层仿真失败:\n" + ran.stdout + ran.stderr
            )
        LOGGER.info(ran.stdout.strip())
        return ran.stdout


def run_topology_route_and_commit_contract() -> None:
    """证明一拍路由以及十个 gate 的网络级原子 exact-two 提交。"""

    output = _run_testbench(
        r"""
module tb;
  logic clk = 1'b0; always #5 clk = ~clk;
  logic rst;
  logic [1:0] mode_state;
  logic tick_valid, tick_ready, route_flush_valid, route_flush_ready;
  logic [3:0] input_spikes;
  logic tick_rsp_valid, tick_rsp_ready;
  logic [2:0] tick_rsp_status;
  logic [7:0] hidden_spikes, pending_hidden_state;
  logic [1:0] output_spikes;
  logic host_cmd_valid, host_cmd_ready, host_cmd_broadcast;
  logic [2:0] host_cmd_opcode;
  logic [3:0] host_neuron_addr;
  logic [15:0] host_snapshot_commit_id, host_mod_commit_id;
  logic signed [1:0] host_modulator;
  logic [1:0] host_weight_addr;
  logic signed [7:0] host_weight_wdata, host_weight_rdata;
  logic host_rsp_valid, host_rsp_ready;
  logic [2:0] host_rsp_status;
  logic [3:0] host_rsp_neuron_addr;
  logic prune_commit_valid, prune_commit_ready;
  logic [15:0] prune_commit_id;
  logic prune_rsp_valid, prune_rsp_ready;
  logic [2:0] prune_rsp_status;
  logic [15:0] prune_rsp_id;
  logic [39:0] prune_rsp_masks_flat;
  logic busy, protocol_error;
  logic [31:0] commit_epoch_state;
  logic [39:0] issue_masks_flat, structural_masks_flat;
  logic [9:0] mask_valids_state, pending_snapshot_valids_state;
  logic [159:0] pending_snapshot_ids_flat_state, utility_flat_state;
  logic [35:0] network_hidden_dense_reads_state;
  logic [35:0] network_hidden_reads_issued_state;
  logic [35:0] network_hidden_reads_saved_state;
  logic [35:0] network_output_dense_reads_state;
  logic [35:0] network_output_reads_issued_state;
  logic [35:0] network_output_reads_saved_state;

  eneuron_pruned_network_4x8x2 dut(.*);

  function automatic integer popcount4(input logic [3:0] value);
    popcount4 = value[0] + value[1] + value[2] + value[3];
  endfunction

  task automatic launch_tick(input logic [3:0] spikes);
    begin
      input_spikes = spikes;
      tick_valid = 1'b1;
      #1;
      if (!tick_ready)
        $fatal(1, "TICK_NOT_READY");
      @(posedge clk);
      #1 tick_valid = 1'b0;
    end
  endtask

  task automatic wait_tick_rsp;
    integer timeout;
    begin
      timeout = 0;
      while (!tick_rsp_valid && timeout < 400) begin
        @(posedge clk); #1; timeout = timeout + 1;
      end
      if (!tick_rsp_valid || tick_rsp_status != 0)
        $fatal(1, "TICK_RESPONSE_FAILED valid=%0d status=%0d",
               tick_rsp_valid, tick_rsp_status);
      tick_rsp_ready = 1'b1;
      @(posedge clk); #1 tick_rsp_ready = 1'b0;
    end
  endtask

  integer lane;
  integer timeout;
  initial begin
    rst = 1'b1;
    mode_state = 2'd1;
    tick_valid = 1'b0;
    route_flush_valid = 1'b0;
    input_spikes = 4'h0;
    tick_rsp_ready = 1'b0;
    host_cmd_valid = 1'b0;
    host_cmd_opcode = '0;
    host_cmd_broadcast = 1'b0;
    host_neuron_addr = '0;
    host_snapshot_commit_id = '0;
    host_mod_commit_id = '0;
    host_modulator = '0;
    host_weight_addr = '0;
    host_weight_wdata = '0;
    host_rsp_ready = 1'b0;
    prune_commit_valid = 1'b0;
    prune_commit_id = 16'h4101;
    prune_rsp_ready = 1'b0;
    repeat (3) @(posedge clk);
    rst = 1'b0;

    // 首拍 output 消费复位后的旧 pending=0；八个 detector 接相同四输入。
    launch_tick(4'b1111);
    if (issue_masks_flat !== {{2{4'b0000}}, {8{4'b1111}}})
      $fatal(1, "DENSE_ISSUE_MASKS_WRONG masks=%h", issue_masks_flat);
    wait_tick_rsp();
    if (hidden_spikes != 8'hff || output_spikes != 2'b00
        || pending_hidden_state != 8'hff)
      $fatal(1, "FIRST_ROUTE_WRONG hidden=%h output=%b pending=%h",
             hidden_spikes, output_spikes, pending_hidden_state);

    // route flush 只推进两个 output，并消费旧 pending 后将路由清零。
    route_flush_valid = 1'b1;
    #1;
    if (!route_flush_ready || tick_ready)
      $fatal(1, "ROUTE_FLUSH_NOT_EXCLUSIVE flush=%0d tick=%0d",
             route_flush_ready, tick_ready);
    @(posedge clk); #1 route_flush_valid = 1'b0;
    wait_tick_rsp();
    if (hidden_spikes != 8'h00 || output_spikes != 2'b11
        || pending_hidden_state != 8'h00)
      $fatal(1, "ROUTE_FLUSH_WRONG hidden=%h output=%b pending=%h",
             hidden_spikes, output_spikes, pending_hidden_state);

    // 所有 utility 同分时固定保留低编号两路；成功必须在十核 clear 后才公开。
    prune_commit_valid = 1'b1;
    #1;
    if (!prune_commit_ready || tick_ready || route_flush_ready)
      $fatal(1, "COMMIT_PRIORITY_OR_READY_WRONG commit=%0d tick=%0d flush=%0d",
             prune_commit_ready, tick_ready, route_flush_ready);
    @(posedge clk); #1 prune_commit_valid = 1'b0;
    timeout = 0;
    while (!prune_rsp_valid && timeout < 400) begin
      if (tick_ready || route_flush_ready || host_cmd_ready)
        $fatal(1, "RUNTIME_ACCEPTED_DURING_COMMIT");
      @(posedge clk); #1; timeout = timeout + 1;
    end
    if (!prune_rsp_valid || prune_rsp_status != 0 || prune_rsp_id != 16'h4101)
      $fatal(1, "COMMIT_RESPONSE_FAILED valid=%0d status=%0d id=%h",
             prune_rsp_valid, prune_rsp_status, prune_rsp_id);
    if (commit_epoch_state != 1 || mask_valids_state != 10'h3ff)
      $fatal(1, "COMMIT_NOT_PUBLISHED epoch=%0d valid=%h",
             commit_epoch_state, mask_valids_state);
    for (lane = 0; lane < 10; lane = lane + 1) begin
      if (popcount4(structural_masks_flat[lane*4 +: 4]) != 2)
        $fatal(1, "MASK_NOT_EXACT_TWO lane=%0d mask=%b", lane,
               structural_masks_flat[lane*4 +: 4]);
      if (structural_masks_flat[lane*4 +: 4] != 4'b0011)
        $fatal(1, "TIE_BREAK_WRONG lane=%0d mask=%b", lane,
               structural_masks_flat[lane*4 +: 4]);
      if (prune_rsp_masks_flat[lane*4 +: 4]
          != structural_masks_flat[lane*4 +: 4])
        $fatal(1, "RESPONSE_MASK_MISMATCH lane=%0d", lane);
    end

    // 上游背压时完整网络响应必须保持稳定，不能重复提交或提前释放。
    repeat (3) begin
      @(posedge clk); #1;
      if (!prune_rsp_valid || prune_rsp_status != 0
          || prune_rsp_id != 16'h4101 || commit_epoch_state != 1
          || prune_rsp_masks_flat != {10{4'b0011}})
        $fatal(1, "PRUNE_RESPONSE_BACKPRESSURE_UNSTABLE");
    end
    prune_rsp_ready = 1'b1;
    @(posedge clk); #1 prune_rsp_ready = 1'b0;
    if (prune_rsp_valid || busy || protocol_error)
      $fatal(1, "COMMIT_NOT_RELEASED valid=%0d busy=%0d error=%0d",
             prune_rsp_valid, busy, protocol_error);

    $display("NP4B_ENEURON_4X8X2_ROUTE_COMMIT_PASS");
    $finish;
  end
endmodule
"""
    )
    if "NP4B_ENEURON_4X8X2_ROUTE_COMMIT_PASS" not in output:
        raise AssertionError("未看到 ENeuron 4→8→2 路由/提交通过标记")


def run_host_transaction_and_backpressure_contract() -> None:
    """证明广播/寻址 Host 事务和单槽响应背压。"""

    output = _run_testbench(
        r"""
module tb;
  logic clk = 1'b0; always #5 clk = ~clk;
  logic rst;
  logic [1:0] mode_state;
  logic tick_valid, tick_ready, route_flush_valid, route_flush_ready;
  logic [3:0] input_spikes;
  logic tick_rsp_valid, tick_rsp_ready;
  logic [2:0] tick_rsp_status;
  logic [7:0] hidden_spikes, pending_hidden_state;
  logic [1:0] output_spikes;
  logic host_cmd_valid, host_cmd_ready, host_cmd_broadcast;
  logic [2:0] host_cmd_opcode;
  logic [3:0] host_neuron_addr;
  logic [15:0] host_snapshot_commit_id, host_mod_commit_id;
  logic signed [1:0] host_modulator;
  logic [1:0] host_weight_addr;
  logic signed [7:0] host_weight_wdata, host_weight_rdata;
  logic host_rsp_valid, host_rsp_ready;
  logic [2:0] host_rsp_status;
  logic [3:0] host_rsp_neuron_addr;
  logic prune_commit_valid, prune_commit_ready;
  logic [15:0] prune_commit_id;
  logic prune_rsp_valid, prune_rsp_ready;
  logic [2:0] prune_rsp_status;
  logic [15:0] prune_rsp_id;
  logic [39:0] prune_rsp_masks_flat;
  logic busy, protocol_error;
  logic [31:0] commit_epoch_state;
  logic [39:0] issue_masks_flat, structural_masks_flat;
  logic [9:0] mask_valids_state, pending_snapshot_valids_state;
  logic [159:0] pending_snapshot_ids_flat_state, utility_flat_state;
  logic [35:0] network_hidden_dense_reads_state;
  logic [35:0] network_hidden_reads_issued_state;
  logic [35:0] network_hidden_reads_saved_state;
  logic [35:0] network_output_dense_reads_state;
  logic [35:0] network_output_reads_issued_state;
  logic [35:0] network_output_reads_saved_state;

  eneuron_pruned_network_4x8x2 dut(.*);

  task automatic start_host(
      input logic [2:0] opcode,
      input logic broadcast,
      input logic [3:0] address
  );
    begin
      host_cmd_opcode = opcode;
      host_cmd_broadcast = broadcast;
      host_neuron_addr = address;
      host_cmd_valid = 1'b1;
      #1;
      if (!host_cmd_ready || tick_ready || route_flush_ready)
        $fatal(1, "HOST_NOT_EXCLUSIVE ready=%0d tick=%0d flush=%0d",
               host_cmd_ready, tick_ready, route_flush_ready);
      @(posedge clk); #1 host_cmd_valid = 1'b0;
    end
  endtask

  task automatic wait_host_rsp;
    integer timeout;
    begin
      timeout = 0;
      while (!host_rsp_valid && timeout < 400) begin
        @(posedge clk); #1; timeout = timeout + 1;
      end
      if (!host_rsp_valid || host_rsp_status != 0)
        $fatal(1, "HOST_RESPONSE_FAILED valid=%0d status=%0d",
               host_rsp_valid, host_rsp_status);
    end
  endtask

  task automatic release_host_rsp;
    begin
      host_rsp_ready = 1'b1;
      @(posedge clk); #1 host_rsp_ready = 1'b0;
      if (host_rsp_valid)
        $fatal(1, "HOST_RESPONSE_NOT_RELEASED");
    end
  endtask

  integer lane;
  initial begin
    rst = 1'b1;
    mode_state = 2'd1;
    tick_valid = 1'b0;
    route_flush_valid = 1'b0;
    input_spikes = '0;
    tick_rsp_ready = 1'b0;
    host_cmd_valid = 1'b0;
    host_cmd_opcode = '0;
    host_cmd_broadcast = 1'b0;
    host_neuron_addr = '0;
    host_snapshot_commit_id = 16'h5101;
    host_mod_commit_id = 16'h5101;
    host_modulator = 0;
    host_weight_addr = 0;
    host_weight_wdata = 7;
    host_rsp_ready = 1'b0;
    prune_commit_valid = 1'b0;
    prune_commit_id = '0;
    prune_rsp_ready = 1'b0;
    repeat (3) @(posedge clk);
    rst = 1'b0;

    // 可寻址权重写只等待一个神经元；响应在背压期间保持字段和读回值。
    start_host(3'd3, 1'b0, 4'd9);
    wait_host_rsp();
    if (host_rsp_neuron_addr != 9 || host_weight_rdata != 7)
      $fatal(1, "ADDRESSED_WEIGHT_WRONG neuron=%0d weight=%0d",
             host_rsp_neuron_addr, host_weight_rdata);
    repeat (3) begin
      @(posedge clk); #1;
      if (!host_rsp_valid || host_rsp_status != 0
          || host_rsp_neuron_addr != 9 || host_weight_rdata != 7)
        $fatal(1, "HOST_RESPONSE_BACKPRESSURE_UNSTABLE");
    end
    release_host_rsp();

    // 广播 snapshot 必须等待十核全部完成，并公开十份相同 commit ID。
    start_host(3'd1, 1'b1, 4'd0);
    wait_host_rsp();
    if (pending_snapshot_valids_state != 10'h3ff)
      $fatal(1, "BROADCAST_SNAPSHOT_INCOMPLETE valid=%h",
             pending_snapshot_valids_state);
    for (lane = 0; lane < 10; lane = lane + 1)
      if (pending_snapshot_ids_flat_state[lane*16 +: 16] != 16'h5101)
        $fatal(1, "SNAPSHOT_ID_WRONG lane=%0d id=%h", lane,
               pending_snapshot_ids_flat_state[lane*16 +: 16]);
    release_host_rsp();

    // 可寻址零 MOD 只消费 neuron 9 的 pending snapshot，不生成片上调制。
    start_host(3'd2, 1'b0, 4'd9);
    wait_host_rsp();
    if (pending_snapshot_valids_state != 10'h1ff)
      $fatal(1, "ADDRESSED_MOD_WRONG pending=%h",
             pending_snapshot_valids_state);
    release_host_rsp();

    if (busy || protocol_error || commit_epoch_state != 0)
      $fatal(1, "HOST_CHANGED_UNRELATED_STATE busy=%0d error=%0d epoch=%0d",
             busy, protocol_error, commit_epoch_state);
    $display("NP4B_ENEURON_4X8X2_HOST_PASS");
    $finish;
  end
endmodule
"""
    )
    if "NP4B_ENEURON_4X8X2_HOST_PASS" not in output:
        raise AssertionError("未看到 ENeuron 4→8→2 Host 合同通过标记")


def run_hidden_output_accounting_contract() -> None:
    """证明八个 hidden 与两个 output 的 dense/issued/saved 不串账。"""

    output = _run_testbench(
        r"""
module tb;
  logic clk = 1'b0; always #5 clk = ~clk;
  logic rst;
  logic [1:0] mode_state;
  logic tick_valid, tick_ready, route_flush_valid;
  logic [3:0] input_spikes;
  logic tick_rsp_valid, tick_rsp_ready;
  logic host_cmd_valid, host_cmd_ready, host_cmd_broadcast;
  logic [2:0] host_cmd_opcode;
  logic [3:0] host_neuron_addr;
  logic [15:0] host_snapshot_commit_id, host_mod_commit_id;
  logic signed [1:0] host_modulator;
  logic [1:0] host_weight_addr;
  logic signed [7:0] host_weight_wdata;
  logic host_rsp_valid, host_rsp_ready;
  logic prune_commit_valid, prune_commit_ready;
  logic [15:0] prune_commit_id;
  logic prune_rsp_valid, prune_rsp_ready;
  logic [2:0] prune_rsp_status;
  logic [35:0] network_hidden_dense_reads_state;
  logic [35:0] network_hidden_reads_issued_state;
  logic [35:0] network_hidden_reads_saved_state;
  logic [35:0] network_output_dense_reads_state;
  logic [35:0] network_output_reads_issued_state;
  logic [35:0] network_output_reads_saved_state;

  eneuron_pruned_network_4x8x2 dut (
    .clk(clk), .rst(rst), .mode_state(mode_state),
    .tick_valid(tick_valid), .tick_ready(tick_ready),
    .route_flush_valid(route_flush_valid), .input_spikes(input_spikes),
    .tick_rsp_valid(tick_rsp_valid), .tick_rsp_ready(tick_rsp_ready),
    .host_cmd_valid(host_cmd_valid), .host_cmd_ready(host_cmd_ready),
    .host_cmd_opcode(host_cmd_opcode),
    .host_cmd_broadcast(host_cmd_broadcast),
    .host_neuron_addr(host_neuron_addr),
    .host_snapshot_commit_id(host_snapshot_commit_id),
    .host_mod_commit_id(host_mod_commit_id), .host_modulator(host_modulator),
    .host_weight_addr(host_weight_addr), .host_weight_wdata(host_weight_wdata),
    .host_rsp_valid(host_rsp_valid), .host_rsp_ready(host_rsp_ready),
    .prune_commit_valid(prune_commit_valid),
    .prune_commit_ready(prune_commit_ready), .prune_commit_id(prune_commit_id),
    .prune_rsp_valid(prune_rsp_valid), .prune_rsp_ready(prune_rsp_ready),
    .prune_rsp_status(prune_rsp_status),
    .network_hidden_dense_reads_state(network_hidden_dense_reads_state),
    .network_hidden_reads_issued_state(network_hidden_reads_issued_state),
    .network_hidden_reads_saved_state(network_hidden_reads_saved_state),
    .network_output_dense_reads_state(network_output_dense_reads_state),
    .network_output_reads_issued_state(network_output_reads_issued_state),
    .network_output_reads_saved_state(network_output_reads_saved_state)
  );

  task automatic host_weight_broadcast(
      input logic [1:0] address,
      input logic signed [7:0] value
  );
    integer timeout;
    begin
      host_cmd_opcode = 3'd3;
      host_cmd_broadcast = 1'b1;
      host_weight_addr = address;
      host_weight_wdata = value;
      host_cmd_valid = 1'b1;
      #1;
      if (!host_cmd_ready)
        $fatal(1, "WEIGHT_BROADCAST_NOT_READY");
      @(posedge clk); #1 host_cmd_valid = 1'b0;
      timeout = 0;
      while (!host_rsp_valid && timeout < 400) begin
        @(posedge clk); #1; timeout = timeout + 1;
      end
      if (!host_rsp_valid)
        $fatal(1, "WEIGHT_BROADCAST_NO_RESPONSE");
      host_rsp_ready = 1'b1;
      @(posedge clk); #1 host_rsp_ready = 1'b0;
    end
  endtask

  task automatic network_commit;
    integer timeout;
    begin
      prune_commit_valid = 1'b1;
      #1;
      if (!prune_commit_ready)
        $fatal(1, "COMMIT_NOT_READY");
      @(posedge clk); #1 prune_commit_valid = 1'b0;
      timeout = 0;
      while (!prune_rsp_valid && timeout < 400) begin
        @(posedge clk); #1; timeout = timeout + 1;
      end
      if (!prune_rsp_valid || prune_rsp_status != 0)
        $fatal(1, "COMMIT_FAILED valid=%0d status=%0d",
               prune_rsp_valid, prune_rsp_status);
      prune_rsp_ready = 1'b1;
      @(posedge clk); #1 prune_rsp_ready = 1'b0;
    end
  endtask

  task automatic network_tick(input logic [3:0] spikes);
    integer timeout;
    begin
      input_spikes = spikes;
      tick_valid = 1'b1;
      #1;
      if (!tick_ready)
        $fatal(1, "TICK_NOT_READY");
      @(posedge clk); #1 tick_valid = 1'b0;
      timeout = 0;
      while (!tick_rsp_valid && timeout < 400) begin
        @(posedge clk); #1; timeout = timeout + 1;
      end
      if (!tick_rsp_valid)
        $fatal(1, "TICK_NO_RESPONSE");
      tick_rsp_ready = 1'b1;
      @(posedge clk); #1 tick_rsp_ready = 1'b0;
    end
  endtask

  initial begin
    rst = 1'b1;
    mode_state = 2'd1;
    tick_valid = 1'b0;
    route_flush_valid = 1'b0;
    input_spikes = '0;
    tick_rsp_ready = 1'b0;
    host_cmd_valid = 1'b0;
    host_cmd_opcode = '0;
    host_cmd_broadcast = 1'b0;
    host_neuron_addr = 0;
    host_snapshot_commit_id = 0;
    host_mod_commit_id = 0;
    host_modulator = 0;
    host_weight_addr = 0;
    host_weight_wdata = 0;
    host_rsp_ready = 1'b0;
    prune_commit_valid = 1'b0;
    prune_commit_id = 16'h6201;
    prune_rsp_ready = 1'b0;
    repeat (3) @(posedge clk);
    rst = 1'b0;

    // 提高保留的 lane 0/1 权重，使剪枝后八个 detector 仍可形成 pending=ff。
    host_weight_broadcast(2'd0, 8'sd4);
    host_weight_broadcast(2'd1, 8'sd4);
    network_commit();

    network_tick(4'b1111);
    if (network_hidden_dense_reads_state != 32
        || network_hidden_reads_issued_state != 16
        || network_hidden_reads_saved_state != 16)
      $fatal(1, "HIDDEN_ACCOUNT_WRONG dense=%0d issued=%0d saved=%0d",
             network_hidden_dense_reads_state,
             network_hidden_reads_issued_state,
             network_hidden_reads_saved_state);
    if (network_output_dense_reads_state != 0
        || network_output_reads_issued_state != 0
        || network_output_reads_saved_state != 0)
      $fatal(1, "OUTPUT_ACCOUNT_CHANGED_EARLY");

    network_tick(4'b0000);
    if (network_hidden_dense_reads_state != 32
        || network_hidden_reads_issued_state != 16
        || network_hidden_reads_saved_state != 16)
      $fatal(1, "OUTPUT_TICK_CHANGED_HIDDEN_ACCOUNT");
    if (network_output_dense_reads_state != 8
        || network_output_reads_issued_state != 4
        || network_output_reads_saved_state != 4)
      $fatal(1, "OUTPUT_ACCOUNT_WRONG dense=%0d issued=%0d saved=%0d",
             network_output_dense_reads_state,
             network_output_reads_issued_state,
             network_output_reads_saved_state);

    $display("NP4B_ENEURON_4X8X2_LAYER_ACCOUNTING_PASS");
    $finish;
  end
endmodule
"""
    )
    if "NP4B_ENEURON_4X8X2_LAYER_ACCOUNTING_PASS" not in output:
        raise AssertionError("未看到 ENeuron 4→8→2 分层账本通过标记")

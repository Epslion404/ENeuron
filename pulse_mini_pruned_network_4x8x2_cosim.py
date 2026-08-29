"""Pulse-Mini-L/L2 严格 4→8→2 剪枝网络的定向 Icarus 测试。"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from rtl_tile_cosim import find_tool


ROOT = Path(__file__).resolve().parent


def _public_interface_tb(module_name: str) -> str:
    return f"""`timescale 1ns/1ps
module tb;
  logic clk = 0;
  logic rst = 1;
  logic tick_valid = 0;
  logic tick_ready;
  logic route_flush_valid = 0;
  logic route_flush_ready;
  logic [3:0] input_spikes = 0;
  logic [7:0] hidden_train_post = 0;
  logic [1:0] output_train_post = 0;
  logic tick_rsp_valid;
  logic tick_rsp_ready = 0;
  logic [2:0] tick_rsp_status;
  logic [7:0] hidden_spikes;
  logic [1:0] output_spikes;
  logic [7:0] pending_hidden_state;
  logic host_cmd_valid = 0;
  logic host_cmd_ready;
  logic [2:0] host_cmd_opcode = 0;
  logic host_cmd_broadcast = 0;
  logic [3:0] host_neuron_addr = 0;
  logic [7:0] host_cmd_arg0 = 0;
  logic [7:0] host_cmd_arg1 = 0;
  logic host_rsp_valid;
  logic host_rsp_ready = 0;
  logic [2:0] host_rsp_status;
  logic [3:0] host_rsp_neuron_addr;
  logic signed [7:0] host_rsp_data;
  logic host_rsp_spike;
  logic prune_commit_valid = 0;
  logic prune_commit_ready;
  logic [15:0] prune_commit_id = 0;
  logic prune_rsp_valid;
  logic prune_rsp_ready = 0;
  logic [2:0] prune_rsp_status;
  logic [15:0] prune_rsp_id;
  logic [39:0] prune_rsp_masks_flat;
  logic busy;
  logic protocol_error;
  logic [31:0] commit_epoch_state;
  logic [39:0] structural_masks_flat;
  logic [9:0] mask_valids_state;
  logic [9:0] pending_valids_state;
  logic [19:0] mode_states_flat;
  logic [159:0] weights_flat_state;
  logic [79:0] soma_states_flat;
  logic [39:0] refractory_states_flat;
  logic [159:0] pre_age_flat_state;
  logic [79:0] positive_evidence_flat_state;
  logic [79:0] negative_evidence_flat_state;
  logic [159:0] utility_flat_state;
  logic [319:0] observe_counts_flat_state;
  logic [319:0] refractory_skips_flat_state;
  logic [35:0] network_hidden_dense_reads_state;
  logic [35:0] network_hidden_reads_issued_state;
  logic [35:0] network_hidden_reads_saved_state;
  logic [35:0] network_output_dense_reads_state;
  logic [35:0] network_output_reads_issued_state;
  logic [35:0] network_output_reads_saved_state;

  {module_name} dut (.*);
  always #5 clk = ~clk;
  initial begin
    repeat (3) @(posedge clk);
    rst = 0;
    repeat (2) @(posedge clk);
    $display("PULSE_NETWORK_PUBLIC_INTERFACE_PASS");
    $finish;
  end
endmodule
"""


def _sources() -> tuple[Path, ...]:
    return (
        ROOT / "local_prune_gate_2of4.sv",
        ROOT / "local_prune_evidence_gain.sv",
        ROOT / "pulse_mini_prune_bridge.sv",
        ROOT / "pulse_mini_core.sv",
        ROOT / "pulse_mini_l2_core.sv",
        ROOT / "pulse_mini_l_prune_wrapper.sv",
        ROOT / "pulse_mini_l2_prune_wrapper.sv",
        ROOT / "pruned_network_tick_scheduler.sv",
        ROOT / "local_prune_commit_barrier.sv",
        ROOT / "pulse_mini_pruned_network_4x8x2.sv",
        ROOT / "pulse_mini_l_pruned_network_4x8x2.sv",
        ROOT / "pulse_mini_l2_pruned_network_4x8x2.sv",
    )


def compile_public_interfaces() -> None:
    """L/L2 薄顶层必须通过同一组公开端口编译。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    with tempfile.TemporaryDirectory(prefix="pulse_pruned_network_interface_") as temp:
        work = Path(temp)
        for module_name in (
            "pulse_mini_l_pruned_network_4x8x2",
            "pulse_mini_l2_pruned_network_4x8x2",
        ):
            tb = work / f"tb_{module_name}.sv"
            sim = work / f"{module_name}.vvp"
            tb.write_text(_public_interface_tb(module_name), encoding="utf-8")
            compiled = subprocess.run(
                [str(iverilog), "-g2012", "-Wall", "-s", "tb", "-o", str(sim),
                 *(str(path) for path in _sources()), str(tb)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            if compiled.returncode:
                raise RuntimeError(compiled.stdout + compiled.stderr)
            ran = subprocess.run(
                [str(vvp), str(sim)], cwd=ROOT,
                capture_output=True, text=True, check=False,
            )
            if ran.returncode or "PULSE_NETWORK_PUBLIC_INTERFACE_PASS" not in ran.stdout:
                raise RuntimeError(ran.stdout + ran.stderr)


def _network_contract_tb(module_name: str) -> str:
    return _public_interface_tb(module_name).replace(
        "  initial begin\n    repeat (3) @(posedge clk);\n    rst = 0;\n"
        "    repeat (2) @(posedge clk);\n"
        "    $display(\"PULSE_NETWORK_PUBLIC_INTERFACE_PASS\");\n"
        "    $finish;\n  end\nendmodule\n",
        r"""
  function automatic integer popcount4(input logic [3:0] value);
    popcount4 = value[0] + value[1] + value[2] + value[3];
  endfunction

  task automatic host_command(
      input integer opcode, input integer broadcast, input integer address,
      input integer arg0, input integer arg1);
    integer guard;
    begin
      @(negedge clk);
      host_cmd_opcode = opcode[2:0];
      host_cmd_broadcast = broadcast[0];
      host_neuron_addr = address[3:0];
      host_cmd_arg0 = arg0[7:0];
      host_cmd_arg1 = arg1[7:0];
      host_cmd_valid = 1;
      #1;
      guard = 0;
      while (!host_cmd_ready) begin
        @(negedge clk); #1;
        guard = guard + 1;
        if (guard > 60) $fatal(1, "HOST_READY_TIMEOUT op=%0d", opcode);
      end
      if (tick_ready || route_flush_ready)
        $fatal(1, "HOST_NOT_EXCLUSIVE");
      @(posedge clk); #1;
      host_cmd_valid = 0;
      guard = 0;
      while (!host_rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 160) $fatal(1, "HOST_RSP_TIMEOUT op=%0d", opcode);
      end
      if (host_rsp_status != 0)
        $fatal(1, "HOST_RSP_ERROR op=%0d status=%0d", opcode, host_rsp_status);
      if (!broadcast && host_rsp_neuron_addr != address)
        $fatal(1, "HOST_ADDRESS_MISMATCH got=%0d expected=%0d",
          host_rsp_neuron_addr, address);
      repeat (2) begin
        @(posedge clk); #1;
        if (!host_rsp_valid || host_rsp_status != 0)
          $fatal(1, "HOST_BACKPRESSURE_UNSTABLE op=%0d", opcode);
      end
      host_rsp_ready = 1;
      @(posedge clk); #1;
      host_rsp_ready = 0;
    end
  endtask

  task automatic network_tick(
      input logic [3:0] spikes,
      input logic [7:0] hidden_post,
      input logic [1:0] output_post);
    integer guard;
    begin
      @(negedge clk);
      input_spikes = spikes;
      hidden_train_post = hidden_post;
      output_train_post = output_post;
      tick_valid = 1;
      #1;
      guard = 0;
      while (!tick_ready) begin
        @(negedge clk); #1;
        guard = guard + 1;
        if (guard > 60) $fatal(1, "TICK_READY_TIMEOUT");
      end
      @(posedge clk); #1;
      tick_valid = 0;
      guard = 0;
      while (!tick_rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 160) $fatal(1, "TICK_RSP_TIMEOUT");
      end
      if (tick_rsp_status != 0)
        $fatal(1, "TICK_RSP_ERROR status=%0d", tick_rsp_status);
      tick_rsp_ready = 1;
      @(posedge clk); #1;
      tick_rsp_ready = 0;
    end
  endtask

  task automatic route_flush(input logic [1:0] output_post);
    integer guard;
    begin
      @(negedge clk);
      output_train_post = output_post;
      route_flush_valid = 1;
      #1;
      guard = 0;
      while (!route_flush_ready) begin
        @(negedge clk); #1;
        guard = guard + 1;
        if (guard > 60) $fatal(1, "FLUSH_READY_TIMEOUT");
      end
      if (tick_ready) $fatal(1, "FLUSH_NOT_EXCLUSIVE");
      @(posedge clk); #1;
      route_flush_valid = 0;
      guard = 0;
      while (!tick_rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 160) $fatal(1, "FLUSH_RSP_TIMEOUT");
      end
      if (tick_rsp_status != 0)
        $fatal(1, "FLUSH_RSP_ERROR status=%0d", tick_rsp_status);
      tick_rsp_ready = 1;
      @(posedge clk); #1;
      tick_rsp_ready = 0;
    end
  endtask

  task automatic network_commit;
    integer guard;
    begin
      @(negedge clk);
      prune_commit_id = 16'h6201;
      prune_commit_valid = 1;
      #1;
      if (!prune_commit_ready || tick_ready || route_flush_ready || host_cmd_ready)
        $fatal(1, "COMMIT_PRIORITY_OR_READY_WRONG");
      @(posedge clk); #1;
      prune_commit_valid = 0;
      guard = 0;
      while (!prune_rsp_valid) begin
        if (tick_ready || route_flush_ready || host_cmd_ready)
          $fatal(1, "RUNTIME_ACCEPTED_DURING_COMMIT");
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 240) $fatal(1, "COMMIT_RSP_TIMEOUT");
      end
      if (prune_rsp_status != 0 || prune_rsp_id != 16'h6201)
        $fatal(1, "COMMIT_RSP_ERROR status=%0d id=%h",
          prune_rsp_status, prune_rsp_id);
    end
  endtask

  integer lane;
  initial begin
    repeat (3) @(posedge clk);
    rst = 0;

    for (lane = 0; lane < 4; lane = lane + 1)
      host_command(5, 1, 0, lane, 2);
    host_command(0, 1, 0, 1, 0);
    if (mode_states_flat != {10{2'd1}})
      $fatal(1, "MODE_BROADCAST_FAILED modes=%h", mode_states_flat);

    // 首拍 output 必须读取旧 pending=0，hidden 读取当前四输入。
    network_tick(4'b1111, 8'hff, 2'b00);
    if (hidden_spikes != 8'hff || output_spikes != 0
        || pending_hidden_state != 8'hff)
      $fatal(1, "ONE_TICK_ROUTE_FAILED hidden=%h output=%b pending=%h",
        hidden_spikes, output_spikes, pending_hidden_state);

    // flush 只推进 output，消费旧 pending 后清空路由。
    route_flush(2'b11);
    if (hidden_spikes != 0 || output_spikes != 2'b11
        || pending_hidden_state != 0)
      $fatal(1, "ROUTE_FLUSH_FAILED hidden=%h output=%b pending=%h",
        hidden_spikes, output_spikes, pending_hidden_state);
    if (network_hidden_dense_reads_state != 32
        || network_hidden_reads_issued_state != 32
        || network_hidden_reads_saved_state != 0
        || network_output_dense_reads_state != 8
        || network_output_reads_issued_state != 8
        || network_output_reads_saved_state != 0)
      $fatal(1, "DENSE_ACCOUNTING_FAILED hd=%0d hi=%0d hs=%0d od=%0d oi=%0d os=%0d",
        network_hidden_dense_reads_state, network_hidden_reads_issued_state,
        network_hidden_reads_saved_state, network_output_dense_reads_state,
        network_output_reads_issued_state, network_output_reads_saved_state);

    // Host 广播与寻址 CAPTURE/FEEDBACK 都走原 Pulse opcode。
    host_command(3, 1, 0, 0, 0);
    if (pending_valids_state != 10'h3ff)
      $fatal(1, "CAPTURE_BROADCAST_FAILED pending=%h", pending_valids_state);
    host_command(4, 1, 0, 1, 0);
    if (pending_valids_state != 0)
      $fatal(1, "FEEDBACK_BROADCAST_FAILED pending=%h", pending_valids_state);
    for (lane = 0; lane < 10; lane = lane + 1)
      if (observe_counts_flat_state[lane*32 +: 32] != 1)
        $fatal(1, "BROADCAST_OBSERVE_COUNT_WRONG lane=%0d count=%0d",
          lane, observe_counts_flat_state[lane*32 +: 32]);
    host_command(3, 0, 9, 0, 0);
    if (pending_valids_state != 10'h200)
      $fatal(1, "ADDRESSED_CAPTURE_FAILED pending=%h", pending_valids_state);
    host_command(4, 0, 9, 1, 0);
    if (pending_valids_state != 0
        || observe_counts_flat_state[9*32 +: 32] != 2)
      $fatal(1, "ADDRESSED_FEEDBACK_FAILED pending=%h count=%0d",
        pending_valids_state, observe_counts_flat_state[9*32 +: 32]);

    network_commit();
    if (commit_epoch_state != 1 || mask_valids_state != 10'h3ff)
      $fatal(1, "COMMIT_NOT_PUBLISHED epoch=%0d valid=%h",
        commit_epoch_state, mask_valids_state);
    for (lane = 0; lane < 10; lane = lane + 1) begin
      if (popcount4(structural_masks_flat[lane*4 +: 4]) != 2
          || structural_masks_flat[lane*4 +: 4] != 4'b0011
          || prune_rsp_masks_flat[lane*4 +: 4] != 4'b0011)
        $fatal(1, "MASK_NOT_EXACT_TWO lane=%0d mask=%b rsp=%b", lane,
          structural_masks_flat[lane*4 +: 4],
          prune_rsp_masks_flat[lane*4 +: 4]);
    end
    if (pending_valids_state != 0 || soma_states_flat != 0
        || refractory_states_flat != 0 || pre_age_flat_state != 0
        || positive_evidence_flat_state != 0
        || negative_evidence_flat_state != 0)
      $fatal(1, "COMMIT_RESPONSE_PRECEDED_TEN_CORE_CLEAR");
    if (utility_flat_state == 0)
      $fatal(1, "STATE_CLEAR_ERASED_UTILITY");
    repeat (3) begin
      @(posedge clk); #1;
      if (!prune_rsp_valid || prune_rsp_status != 0
          || prune_rsp_id != 16'h6201 || commit_epoch_state != 1
          || prune_rsp_masks_flat != {10{4'b0011}})
        $fatal(1, "COMMIT_BACKPRESSURE_UNSTABLE");
    end
    prune_rsp_ready = 1;
    @(posedge clk); #1;
    prune_rsp_ready = 0;

    // 提交后再跑两拍，分别验证 hidden/output 结构节省和不应期不串账。
    network_tick(4'b1111, 8'h00, 2'b00);
    if (hidden_spikes != 8'hff || output_spikes != 0
        || pending_hidden_state != 8'hff)
      $fatal(1, "SPARSE_FIRST_ROUTE_FAILED");
    network_tick(4'b1111, 8'h00, 2'b00);
    if (output_spikes != 2'b11)
      $fatal(1, "SPARSE_SECOND_ROUTE_FAILED output=%b", output_spikes);
    if (network_hidden_dense_reads_state != 64
        || network_hidden_reads_issued_state != 48
        || network_hidden_reads_saved_state != 16
        || network_output_dense_reads_state != 16
        || network_output_reads_issued_state != 12
        || network_output_reads_saved_state != 4)
      $fatal(1, "SPARSE_ACCOUNTING_FAILED hd=%0d hi=%0d hs=%0d od=%0d oi=%0d os=%0d",
        network_hidden_dense_reads_state, network_hidden_reads_issued_state,
        network_hidden_reads_saved_state, network_output_dense_reads_state,
        network_output_reads_issued_state, network_output_reads_saved_state);
    for (lane = 0; lane < 8; lane = lane + 1)
      if (refractory_skips_flat_state[lane*32 +: 32] != 1)
        $fatal(1, "HIDDEN_REFRACTORY_SKIP_WRONG lane=%0d count=%0d", lane,
          refractory_skips_flat_state[lane*32 +: 32]);

    if (busy || protocol_error)
      $fatal(1, "NETWORK_FINAL_STATE_ERROR busy=%0d protocol=%0d",
        busy, protocol_error);
    $display("PULSE_NETWORK_CONTRACT_PASS module=%m");
    $finish;
  end
endmodule
""",
    )


def run_network_contract() -> None:
    """验证 L/L2 共用控制面的路由、训练、commit-clear 与分账。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    with tempfile.TemporaryDirectory(prefix="pulse_pruned_network_contract_") as temp:
        work = Path(temp)
        for module_name in (
            "pulse_mini_l_pruned_network_4x8x2",
            "pulse_mini_l2_pruned_network_4x8x2",
        ):
            tb = work / f"tb_{module_name}.sv"
            sim = work / f"{module_name}.vvp"
            tb.write_text(_network_contract_tb(module_name), encoding="utf-8")
            compiled = subprocess.run(
                [str(iverilog), "-g2012", "-Wall", "-s", "tb", "-o", str(sim),
                 *(str(path) for path in _sources()), str(tb)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            if compiled.returncode:
                raise RuntimeError(compiled.stdout + compiled.stderr)
            ran = subprocess.run(
                [str(vvp), str(sim)], cwd=ROOT,
                capture_output=True, text=True, check=False,
            )
            if ran.returncode or "PULSE_NETWORK_CONTRACT_PASS" not in ran.stdout:
                raise RuntimeError(ran.stdout + ran.stderr)


def _host_error_and_latching_tb(module_name: str) -> str:
    return _public_interface_tb(module_name).replace(
        "  initial begin\n    repeat (3) @(posedge clk);\n    rst = 0;\n"
        "    repeat (2) @(posedge clk);\n"
        "    $display(\"PULSE_NETWORK_PUBLIC_INTERFACE_PASS\");\n"
        "    $finish;\n  end\nendmodule\n",
        r"""
  task automatic launch_host(
      input integer opcode, input integer broadcast, input integer address,
      input integer arg0, input integer arg1);
    integer guard;
    begin
      @(negedge clk);
      host_cmd_opcode = opcode[2:0];
      host_cmd_broadcast = broadcast[0];
      host_neuron_addr = address[3:0];
      host_cmd_arg0 = arg0[7:0];
      host_cmd_arg1 = arg1[7:0];
      host_cmd_valid = 1;
      #1;
      guard = 0;
      while (!host_cmd_ready) begin
        @(negedge clk); #1;
        guard = guard + 1;
        if (guard > 40) $fatal(1, "HOST_READY_TIMEOUT");
      end
      @(posedge clk); #1;
      host_cmd_valid = 0;
    end
  endtask

  task automatic wait_host(input integer expected_status);
    integer guard;
    begin
      guard = 0;
      while (!host_rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 80) $fatal(1, "HOST_RSP_TIMEOUT");
      end
      if (host_rsp_status != expected_status)
        $fatal(1, "HOST_STATUS_MISMATCH got=%0d expected=%0d",
          host_rsp_status, expected_status);
      host_rsp_ready = 1;
      @(posedge clk); #1;
      host_rsp_ready = 0;
    end
  endtask

  initial begin
    repeat (3) @(posedge clk);
    rst = 0;

    // 核心 BAD_ARG=010 必须被网络识别为非零错误，而非只查看 status[0]。
    launch_host(5, 0, 0, 0, 8);
    wait_host(2);

    // 配置 neuron 9 的 weight0，随后读事务接受后扰动所有 live Host 字段。
    launch_host(5, 0, 9, 0, 3);
    wait_host(0);
    launch_host(6, 0, 9, 0, 0);
    host_cmd_broadcast = 1;
    host_neuron_addr = 0;
    host_cmd_opcode = 0;
    host_cmd_arg0 = 8'hff;
    host_cmd_arg1 = 8'hff;
    wait_host(0);
    if (host_rsp_neuron_addr != 9 || host_rsp_data != 3)
      $fatal(1, "ACCEPTED_HOST_FIELDS_NOT_LATCHED neuron=%0d data=%0d",
        host_rsp_neuron_addr, host_rsp_data);

    $display("PULSE_NETWORK_HOST_ERROR_LATCH_PASS module=%m");
    $finish;
  end
endmodule
""",
    )


def run_host_error_and_latching_contract() -> None:
    """验证任意非零核心状态传播及 Host 接受沿字段锁存。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    with tempfile.TemporaryDirectory(prefix="pulse_pruned_network_host_error_") as temp:
        work = Path(temp)
        for module_name in (
            "pulse_mini_l_pruned_network_4x8x2",
            "pulse_mini_l2_pruned_network_4x8x2",
        ):
            tb = work / f"tb_{module_name}.sv"
            sim = work / f"{module_name}.vvp"
            tb.write_text(_host_error_and_latching_tb(module_name), encoding="utf-8")
            compiled = subprocess.run(
                [str(iverilog), "-g2012", "-Wall", "-s", "tb", "-o", str(sim),
                 *(str(path) for path in _sources()), str(tb)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            if compiled.returncode:
                raise RuntimeError(compiled.stdout + compiled.stderr)
            ran = subprocess.run(
                [str(vvp), str(sim)], cwd=ROOT,
                capture_output=True, text=True, check=False,
            )
            if ran.returncode or "PULSE_NETWORK_HOST_ERROR_LATCH_PASS" not in ran.stdout:
                raise RuntimeError(ran.stdout + ran.stderr)


__all__ = [
    "compile_public_interfaces",
    "run_host_error_and_latching_contract",
    "run_network_contract",
]

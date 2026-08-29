"""十组剪枝 commit→clear 原子屏障的 Icarus 定向验证。"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from rtl_tile_cosim import find_tool


ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("local_prune_commit_barrier_cosim")


def _run_testbench(source: str) -> str:
    """编译并运行一个只通过模块公开端口观察行为的 testbench。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("Icarus Verilog 工具不可用")

    with tempfile.TemporaryDirectory(prefix="np4b_barrier_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "sim.out"
        tb_path.write_text(source, encoding="utf-8")
        compile_result = subprocess.run(
            [
                os.fspath(iverilog),
                "-g2012",
                "-s",
                "tb",
                "-o",
                os.fspath(sim_path),
                os.fspath(ROOT / "local_prune_commit_barrier.sv"),
                os.fspath(tb_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if compile_result.returncode != 0:
            raise AssertionError(
                "commit barrier 编译失败:\n"
                + compile_result.stdout
                + compile_result.stderr
            )
        run_result = subprocess.run(
            [os.fspath(vvp), os.fspath(sim_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if run_result.returncode != 0:
            raise AssertionError(
                "commit barrier 仿真失败:\n" + run_result.stdout + run_result.stderr
            )
        LOGGER.info(run_result.stdout.strip())
        return run_result.stdout


def run_unsafe_precheck_contract() -> None:
    """一个 gate 或 clear 参与者未就绪时，整笔提交返回 UNSAFE。"""

    output = _run_testbench(
        r"""
module tb;
  localparam integer N = 10;
  logic clk = 1'b0; always #5 clk = ~clk;
  logic rst;
  logic commit_valid, commit_ready, safe_boundary;
  logic [15:0] commit_id;
  logic rsp_valid, rsp_ready;
  logic [2:0] rsp_status;
  logic [15:0] rsp_id;
  logic [N*4-1:0] rsp_masks_flat;
  logic runtime_blocked, internal_error;
  logic [31:0] commit_epoch_state;
  logic [N-1:0] gate_cmd_valid, gate_cmd_ready;
  logic [15:0] gate_cmd_id;
  logic [N-1:0] gate_rsp_valid, gate_rsp_ready;
  logic [N*3-1:0] gate_rsp_status_flat;
  logic [N*4-1:0] gate_rsp_masks_flat;
  logic [N-1:0] clear_cmd_valid, clear_cmd_ready;
  logic [N-1:0] clear_rsp_valid, clear_rsp_ready;
  logic [N*3-1:0] clear_rsp_status_flat;

  local_prune_commit_barrier #(.N_GATES(N)) dut(.*);

  initial begin
    rst = 1'b1;
    commit_valid = 1'b0;
    commit_id = 16'h1234;
    safe_boundary = 1'b1;
    rsp_ready = 1'b1;
    gate_cmd_ready = {N{1'b1}};
    clear_cmd_ready = {N{1'b1}};
    gate_rsp_valid = '0;
    gate_rsp_status_flat = '0;
    gate_rsp_masks_flat = '0;
    clear_rsp_valid = '0;
    clear_rsp_status_flat = '0;
    repeat (2) @(posedge clk);
    rst = 1'b0;

    // gate 4 未就绪：整笔命令可被屏障接收并拒绝，但不能启动任何 gate。
    gate_cmd_ready[4] = 1'b0;
    commit_valid = 1'b1;
    @(posedge clk);
    #1;
    commit_valid = 1'b0;
    if (gate_cmd_valid !== '0)
      $fatal(1, "PARTIAL_GATE_START gate_cmd_valid=%h", gate_cmd_valid);
    if (!rsp_valid || rsp_status != 3'd1 || rsp_id != 16'h1234)
      $fatal(1, "EXPECTED_UNSAFE status=%0d valid=%0d id=%h",
             rsp_status, rsp_valid, rsp_id);
    if (commit_epoch_state != 0 || internal_error)
      $fatal(1, "UNSAFE_CHANGED_STATE epoch=%0d internal_error=%0d",
             commit_epoch_state, internal_error);
    $display("NP4B_BARRIER_UNSAFE_PRECHECK_PASS");
    $finish;
  end
endmodule
"""
    )
    if "NP4B_BARRIER_UNSAFE_PRECHECK_PASS" not in output:
        raise AssertionError("未看到屏障 UNSAFE 合同通过标记")


def run_atomic_commit_then_clear_contract() -> None:
    """gate 和 clear 响应可错拍到达，但成功只能在两个屏障后公开。"""

    output = _run_testbench(
        r"""
module tb;
  localparam integer N = 10;
  logic clk = 1'b0; always #5 clk = ~clk;
  logic rst;
  logic commit_valid, commit_ready, safe_boundary;
  logic [15:0] commit_id;
  logic rsp_valid, rsp_ready;
  logic [2:0] rsp_status;
  logic [15:0] rsp_id;
  logic [N*4-1:0] rsp_masks_flat;
  logic runtime_blocked, internal_error;
  logic [31:0] commit_epoch_state;
  logic [N-1:0] gate_cmd_valid, gate_cmd_ready;
  logic [15:0] gate_cmd_id;
  logic [N-1:0] gate_rsp_valid, gate_rsp_ready;
  logic [N*3-1:0] gate_rsp_status_flat;
  logic [N*4-1:0] gate_rsp_masks_flat;
  logic [N-1:0] clear_cmd_valid, clear_cmd_ready;
  logic [N-1:0] clear_rsp_valid, clear_rsp_ready;
  logic [N*3-1:0] clear_rsp_status_flat;
  logic [2:0] held_status;
  logic [15:0] held_id;
  logic [N*4-1:0] held_masks;

  local_prune_commit_barrier #(.N_GATES(N)) dut(.*);

  task automatic require_no_external_success;
    begin
      if (rsp_valid)
        $fatal(1, "EARLY_EXTERNAL_RESPONSE status=%0d", rsp_status);
    end
  endtask

  initial begin
    rst = 1'b1;
    commit_valid = 1'b0;
    commit_id = 16'h2201;
    safe_boundary = 1'b1;
    rsp_ready = 1'b0;
    gate_cmd_ready = {N{1'b1}};
    clear_cmd_ready = {N{1'b1}};
    gate_rsp_valid = '0;
    gate_rsp_status_flat = '0;
    gate_rsp_masks_flat = {N{4'b0011}};
    clear_rsp_valid = '0;
    clear_rsp_status_flat = '0;
    repeat (2) @(posedge clk);
    rst = 1'b0;

    commit_valid = 1'b1;
    #1;
    if (gate_cmd_valid !== {N{1'b1}} || gate_cmd_id != commit_id)
      $fatal(1, "GATES_NOT_STARTED_TOGETHER valid=%h id=%h", gate_cmd_valid, gate_cmd_id);
    @(posedge clk);
    #1 commit_valid = 1'b0;
    require_no_external_success();

    gate_rsp_valid = 10'b0000000011;
    @(posedge clk);
    #1 gate_rsp_valid = '0;
    require_no_external_success();

    gate_rsp_valid = 10'b0011111100;
    @(posedge clk);
    #1 gate_rsp_valid = '0;
    require_no_external_success();

    gate_rsp_valid = 10'b1100000000;
    @(posedge clk);
    #1 gate_rsp_valid = '0;
    require_no_external_success();
    if (clear_cmd_valid !== {N{1'b1}})
      $fatal(1, "CLEAR_NOT_ISSUED_TOGETHER valid=%h", clear_cmd_valid);

    @(posedge clk);
    #1;
    if (clear_cmd_valid !== '0)
      $fatal(1, "CLEAR_COMMAND_REPEATED valid=%h", clear_cmd_valid);
    require_no_external_success();

    clear_rsp_valid = 10'b0000011111;
    @(posedge clk);
    #1 clear_rsp_valid = '0;
    require_no_external_success();

    clear_rsp_valid = 10'b1111100000;
    @(posedge clk);
    #1 clear_rsp_valid = '0;
    if (!rsp_valid || rsp_status != 3'd0 || rsp_id != 16'h2201)
      $fatal(1, "FINAL_RESPONSE_MISSING status=%0d valid=%0d id=%h",
             rsp_status, rsp_valid, rsp_id);
    if (rsp_masks_flat !== {N{4'b0011}} || commit_epoch_state != 1)
      $fatal(1, "FINAL_STATE_WRONG masks=%h epoch=%0d",
             rsp_masks_flat, commit_epoch_state);
    if (!runtime_blocked || internal_error)
      $fatal(1, "FINAL_FLAGS_WRONG blocked=%0d internal=%0d",
             runtime_blocked, internal_error);

    held_status = rsp_status;
    held_id = rsp_id;
    held_masks = rsp_masks_flat;
    repeat (3) begin
      @(posedge clk);
      #1;
      if (!rsp_valid || rsp_status != held_status || rsp_id != held_id
          || rsp_masks_flat != held_masks)
        $fatal(1, "RESPONSE_BACKPRESSURE_UNSTABLE");
    end
    rsp_ready = 1'b1;
    @(posedge clk);
    #1;
    if (rsp_valid || runtime_blocked)
      $fatal(1, "RESPONSE_NOT_RELEASED valid=%0d blocked=%0d",
             rsp_valid, runtime_blocked);
    $display("NP4B_BARRIER_COMMIT_CLEAR_PASS");
    $finish;
  end
endmodule
"""
    )
    if "NP4B_BARRIER_COMMIT_CLEAR_PASS" not in output:
        raise AssertionError("未看到 commit→clear 屏障合同通过标记")


def run_clear_failure_halts_contract() -> None:
    """清历史失败后置 sticky internal error，并永久阻止新提交。"""

    output = _run_testbench(
        r"""
module tb;
  localparam integer N = 10;
  logic clk = 1'b0; always #5 clk = ~clk;
  logic rst;
  logic commit_valid, commit_ready, safe_boundary;
  logic [15:0] commit_id;
  logic rsp_valid, rsp_ready;
  logic [2:0] rsp_status;
  logic [15:0] rsp_id;
  logic [N*4-1:0] rsp_masks_flat;
  logic runtime_blocked, internal_error;
  logic [31:0] commit_epoch_state;
  logic [N-1:0] gate_cmd_valid, gate_cmd_ready;
  logic [15:0] gate_cmd_id;
  logic [N-1:0] gate_rsp_valid, gate_rsp_ready;
  logic [N*3-1:0] gate_rsp_status_flat;
  logic [N*4-1:0] gate_rsp_masks_flat;
  logic [N-1:0] clear_cmd_valid, clear_cmd_ready;
  logic [N-1:0] clear_rsp_valid, clear_rsp_ready;
  logic [N*3-1:0] clear_rsp_status_flat;

  local_prune_commit_barrier #(.N_GATES(N)) dut(.*);

  initial begin
    rst = 1'b1;
    commit_valid = 1'b0;
    commit_id = 16'h3301;
    safe_boundary = 1'b1;
    rsp_ready = 1'b1;
    gate_cmd_ready = {N{1'b1}};
    clear_cmd_ready = {N{1'b1}};
    gate_rsp_valid = '0;
    gate_rsp_status_flat = '0;
    gate_rsp_masks_flat = {N{4'b0101}};
    clear_rsp_valid = '0;
    clear_rsp_status_flat = '0;
    repeat (2) @(posedge clk);
    rst = 1'b0;

    commit_valid = 1'b1;
    @(posedge clk);
    #1 commit_valid = 1'b0;
    gate_rsp_valid = {N{1'b1}};
    @(posedge clk);
    #1 gate_rsp_valid = '0;
    if (clear_cmd_valid !== {N{1'b1}})
      $fatal(1, "CLEAR_NOT_ISSUED");
    @(posedge clk);
    #1;

    clear_rsp_status_flat[6*3 +: 3] = 3'd5;
    clear_rsp_valid = {N{1'b1}};
    @(posedge clk);
    #1 clear_rsp_valid = '0;
    if (!rsp_valid || rsp_status != 3'd2 || !internal_error || !runtime_blocked)
      $fatal(1, "HALT_NOT_VISIBLE valid=%0d status=%0d internal=%0d blocked=%0d",
             rsp_valid, rsp_status, internal_error, runtime_blocked);
    if (commit_epoch_state != 0 || commit_ready)
      $fatal(1, "FAILED_CLEAR_PUBLISHED epoch=%0d ready=%0d",
             commit_epoch_state, commit_ready);

    commit_id = 16'h3302;
    commit_valid = 1'b1;
    repeat (3) begin
      @(posedge clk);
      #1;
      if (commit_ready || !internal_error || !runtime_blocked)
        $fatal(1, "HALT_NOT_STICKY");
    end
    $display("NP4B_BARRIER_CLEAR_FAILURE_HALT_PASS");
    $finish;
  end
endmodule
"""
    )
    if "NP4B_BARRIER_CLEAR_FAILURE_HALT_PASS" not in output:
        raise AssertionError("未看到清历史失败 sticky halt 通过标记")

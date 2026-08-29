"""Pulse-Mini 剪枝 wrapper 的公开接口与定向 Icarus 测试工具。"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from rtl_tile_cosim import find_tool


ROOT = Path(__file__).resolve().parent


def _public_interface_tb(module_name: str, *, l2: bool) -> str:
    evidence_width = 8 if l2 else 4
    direction_width = 12 if l2 else 8
    return f"""`timescale 1ns/1ps
module tb;
  logic clk = 0;
  logic rst = 1;
  logic cmd_valid = 0;
  logic cmd_ready;
  logic [2:0] cmd_opcode = 0;
  logic [7:0] cmd_arg0 = 0;
  logic [7:0] cmd_arg1 = 0;
  logic rsp_valid;
  logic rsp_ready = 0;
  logic [2:0] rsp_status;
  logic signed [7:0] rsp_data;
  logic spike;
  logic prune_cmd_valid = 0;
  logic prune_cmd_ready;
  logic [2:0] prune_cmd_opcode = 0;
  logic [15:0] prune_cmd_id = 0;
  logic prune_rsp_valid;
  logic prune_rsp_ready = 0;
  logic [2:0] prune_rsp_status;
  logic [15:0] prune_rsp_id;
  logic [3:0] prune_rsp_mask;
  logic pending_valid;
  logic protocol_error;
  logic [1:0] mode_state;
  logic signed [3:0] weight0, weight1, weight2, weight3;
  logic signed [7:0] soma_state;
  logic [3:0] refractory_state, leak_timer_state;
  logic [15:0] pre_age_flat;
  logic [3:0] post_age_state;
  logic [{evidence_width - 1}:0] positive_evidence, negative_evidence;
  logic signed [{direction_width - 1}:0] captured_direction_flat;
  logic [15:0] prune_utility_state;
  logic [3:0] prune_structural_mask_state;
  logic prune_mask_valid_state;
  logic [31:0] prune_observe_count_state;
  logic [31:0] prune_refractory_skips_state;
  logic prune_sticky_halt_state;
  logic [7:0] prune_latched_evidence_state;
  logic [31:0] prune_dense_reads_state;
  logic [31:0] prune_reads_issued_state;
  logic [31:0] prune_reads_saved_state;

  {module_name} dut (.*);
  always #5 clk = ~clk;
  initial begin
    repeat (3) @(posedge clk);
    rst = 0;
    repeat (2) @(posedge clk);
    $display("PUBLIC_INTERFACE_PASS");
    $finish;
  end
endmodule
"""


def compile_public_interfaces() -> None:
    """两个 wrapper 都必须只通过公开端口完成编译和实例化。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")

    sources = (
        ROOT / "local_prune_gate_2of4.sv",
        ROOT / "local_prune_evidence_gain.sv",
        ROOT / "pulse_mini_prune_bridge.sv",
        ROOT / "pulse_mini_core.sv",
        ROOT / "pulse_mini_l2_core.sv",
        ROOT / "pulse_mini_l_prune_wrapper.sv",
        ROOT / "pulse_mini_l2_prune_wrapper.sv",
    )
    cases = (
        ("pulse_mini_l_prune_wrapper", False),
        ("pulse_mini_l2_prune_wrapper", True),
    )
    with tempfile.TemporaryDirectory(prefix="pulse_prune_interface_") as temp:
        temp_path = Path(temp)
        for module_name, l2 in cases:
            tb_path = temp_path / f"tb_{module_name}.sv"
            sim_path = temp_path / f"{module_name}.vvp"
            tb_path.write_text(_public_interface_tb(module_name, l2=l2), encoding="utf-8")
            result = subprocess.run(
                [
                    str(iverilog),
                    "-g2012",
                    "-Wall",
                    "-s",
                    "tb",
                    "-o",
                    str(sim_path),
                    *(str(path) for path in sources),
                    str(tb_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            run = subprocess.run(
                [str(vvp), str(sim_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if run.returncode or "PUBLIC_INTERFACE_PASS" not in run.stdout:
                raise RuntimeError(run.stdout + run.stderr)


def _feedback_contract_tb(module_name: str, *, l2: bool) -> str:
    evidence_width = 8 if l2 else 4
    direction_width = 12 if l2 else 8
    expected_utility = 1 if l2 else 2
    return f"""`timescale 1ns/1ps
module tb;
  logic clk = 0;
  logic rst = 1;
  logic cmd_valid = 0;
  logic cmd_ready;
  logic [2:0] cmd_opcode = 0;
  logic [7:0] cmd_arg0 = 0;
  logic [7:0] cmd_arg1 = 0;
  logic rsp_valid;
  logic rsp_ready = 0;
  logic [2:0] rsp_status;
  logic signed [7:0] rsp_data;
  logic spike;
  logic prune_cmd_valid = 0;
  logic prune_cmd_ready;
  logic [2:0] prune_cmd_opcode = 0;
  logic [15:0] prune_cmd_id = 0;
  logic prune_rsp_valid;
  logic prune_rsp_ready = 0;
  logic [2:0] prune_rsp_status;
  logic [15:0] prune_rsp_id;
  logic [3:0] prune_rsp_mask;
  logic pending_valid;
  logic protocol_error;
  logic [1:0] mode_state;
  logic signed [3:0] weight0, weight1, weight2, weight3;
  logic signed [7:0] soma_state;
  logic [3:0] refractory_state, leak_timer_state;
  logic [15:0] pre_age_flat;
  logic [3:0] post_age_state;
  logic [{evidence_width - 1}:0] positive_evidence, negative_evidence;
  logic signed [{direction_width - 1}:0] captured_direction_flat;
  logic [15:0] prune_utility_state;
  logic [3:0] prune_structural_mask_state;
  logic prune_mask_valid_state;
  logic [31:0] prune_observe_count_state;
  logic [31:0] prune_refractory_skips_state;
  logic prune_sticky_halt_state;
  logic [7:0] prune_latched_evidence_state;
  logic [31:0] prune_dense_reads_state;
  logic [31:0] prune_reads_issued_state;
  logic [31:0] prune_reads_saved_state;
  integer before_observe;
  integer stalled_observe;

  {module_name} dut (.*);
  always #5 clk = ~clk;

  task automatic issue_core(
      input integer op, input integer a0, input integer a1,
      input integer expected_status, input integer expected_observe,
      input integer stall_cycles);
    integer guard;
    begin
      @(negedge clk);
      guard = 0;
      while (!cmd_ready) begin
        @(negedge clk);
        guard = guard + 1;
        if (guard > 30) $fatal(1, "cmd_ready timeout op=%0d", op);
      end
      cmd_opcode = op[2:0];
      cmd_arg0 = a0[7:0];
      cmd_arg1 = a1[7:0];
      cmd_valid = 1;
      @(posedge clk); #1;
      cmd_valid = 0;
      guard = 0;
      while (!rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 40) $fatal(1, "response timeout op=%0d", op);
      end
      if (rsp_status != expected_status)
        $fatal(1, "status mismatch op=%0d got=%0d expected=%0d", op, rsp_status, expected_status);
      if (prune_observe_count_state != expected_observe)
        $fatal(1, "observe mismatch op=%0d got=%0d expected=%0d", op,
          prune_observe_count_state, expected_observe);
      stalled_observe = prune_observe_count_state;
      repeat (stall_cycles) begin
        @(posedge clk); #1;
        if (!rsp_valid) $fatal(1, "response dropped under backpressure");
        if (prune_observe_count_state != stalled_observe)
          $fatal(1, "OBSERVE repeated under response backpressure");
      end
      rsp_ready = 1;
      @(posedge clk); #1;
      rsp_ready = 0;
    end
  endtask

  task automatic make_positive_capture;
    begin
      issue_core(1, 0, 0, 0, prune_observe_count_state, 0);
      issue_core(2, 1, 1, 0, prune_observe_count_state, 0);
      issue_core(3, 0, 0, 0, prune_observe_count_state, 0);
      if (captured_direction_flat == 0)
        $fatal(1, "CAPTURE did not produce evidence");
    end
  endtask

  initial begin
    repeat (3) @(posedge clk);
    rst = 0;
    issue_core(0, 1, 0, 0, 0, 0);

    make_positive_capture();
    before_observe = prune_observe_count_state;
    issue_core(4, 1, 0, 0, before_observe + 1, 3);
    if (prune_utility_state[3:0] != {expected_utility})
      $fatal(1, "utility mismatch got=%0d expected={expected_utility}", prune_utility_state[3:0]);
    if (prune_latched_evidence_state[1:0] != {expected_utility})
      $fatal(1, "accepted-edge evidence was not retained");

    // 没有 pending 的失败 FEEDBACK 不能再次观察。
    issue_core(4, 1, 0, 5, before_observe + 1, 0);

    // 零 FEEDBACK 合法消费 pending，但不产生 OBSERVE。
    make_positive_capture();
    issue_core(4, 0, 0, 0, before_observe + 1, 0);

    if (prune_sticky_halt_state)
      $fatal(1, "unexpected sticky halt");
    $display("FEEDBACK_CONTRACT_PASS module={module_name}");
    $finish;
  end
endmodule
"""


def run_feedback_contract() -> None:
    """验证 FEEDBACK 接受沿取证、OBSERVE exactly-once 和响应顺序。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    sources = (
        ROOT / "local_prune_gate_2of4.sv",
        ROOT / "local_prune_evidence_gain.sv",
        ROOT / "pulse_mini_prune_bridge.sv",
        ROOT / "pulse_mini_core.sv",
        ROOT / "pulse_mini_l2_core.sv",
        ROOT / "pulse_mini_l_prune_wrapper.sv",
        ROOT / "pulse_mini_l2_prune_wrapper.sv",
    )
    with tempfile.TemporaryDirectory(prefix="pulse_prune_feedback_") as temp:
        temp_path = Path(temp)
        for module_name, l2 in (
            ("pulse_mini_l_prune_wrapper", False),
            ("pulse_mini_l2_prune_wrapper", True),
        ):
            tb_path = temp_path / f"tb_{module_name}.sv"
            sim_path = temp_path / f"{module_name}.vvp"
            tb_path.write_text(_feedback_contract_tb(module_name, l2=l2), encoding="utf-8")
            compile_result = subprocess.run(
                [str(iverilog), "-g2012", "-Wall", "-s", "tb", "-o", str(sim_path),
                 *(str(path) for path in sources), str(tb_path)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            if compile_result.returncode:
                raise RuntimeError(compile_result.stdout + compile_result.stderr)
            run = subprocess.run(
                [str(vvp), str(sim_path)], cwd=ROOT,
                capture_output=True, text=True, check=False,
            )
            if run.returncode or "FEEDBACK_CONTRACT_PASS" not in run.stdout:
                raise RuntimeError(run.stdout + run.stderr)


def _auto_clear_contract_tb(module_name: str, *, l2: bool, auto_clear: bool) -> str:
    evidence_width = 8 if l2 else 4
    direction_width = 12 if l2 else 8
    auto_clear_bit = 1 if auto_clear else 0
    return f"""`timescale 1ns/1ps
module tb;
  logic clk = 0;
  logic rst = 1;
  logic cmd_valid = 0;
  logic cmd_ready;
  logic [2:0] cmd_opcode = 0;
  logic [7:0] cmd_arg0 = 0;
  logic [7:0] cmd_arg1 = 0;
  logic rsp_valid;
  logic rsp_ready = 0;
  logic [2:0] rsp_status;
  logic signed [7:0] rsp_data;
  logic spike;
  logic prune_cmd_valid = 0;
  logic prune_cmd_ready;
  logic [2:0] prune_cmd_opcode = 0;
  logic [15:0] prune_cmd_id = 0;
  logic prune_rsp_valid;
  logic prune_rsp_ready = 0;
  logic [2:0] prune_rsp_status;
  logic [15:0] prune_rsp_id;
  logic [3:0] prune_rsp_mask;
  logic pending_valid;
  logic protocol_error;
  logic [1:0] mode_state;
  logic signed [3:0] weight0, weight1, weight2, weight3;
  logic signed [7:0] soma_state;
  logic [3:0] refractory_state, leak_timer_state;
  logic [15:0] pre_age_flat;
  logic [3:0] post_age_state;
  logic [{evidence_width - 1}:0] positive_evidence, negative_evidence;
  logic signed [{direction_width - 1}:0] captured_direction_flat;
  logic [15:0] prune_utility_state;
  logic [3:0] prune_structural_mask_state;
  logic prune_mask_valid_state;
  logic [31:0] prune_observe_count_state;
  logic [31:0] prune_refractory_skips_state;
  logic prune_sticky_halt_state;
  logic [7:0] prune_latched_evidence_state;
  logic [31:0] prune_dense_reads_state;
  logic [31:0] prune_reads_issued_state;
  logic [31:0] prune_reads_saved_state;

  {module_name} #(.AUTO_CLEAR_ON_COMMIT(1'b{auto_clear_bit})) dut (.*);
  always #5 clk = ~clk;

  task automatic issue_core(
      input integer op, input integer a0, input integer a1,
      input integer expected_status);
    integer guard;
    begin
      @(negedge clk);
      guard = 0;
      while (!cmd_ready) begin
        @(negedge clk);
        guard = guard + 1;
        if (guard > 30) $fatal(1, "cmd_ready timeout op=%0d", op);
      end
      cmd_opcode = op[2:0];
      cmd_arg0 = a0[7:0];
      cmd_arg1 = a1[7:0];
      cmd_valid = 1;
      @(posedge clk); #1;
      cmd_valid = 0;
      guard = 0;
      while (!rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 40) $fatal(1, "response timeout op=%0d", op);
      end
      if (rsp_status != expected_status)
        $fatal(1, "status mismatch op=%0d got=%0d expected=%0d",
          op, rsp_status, expected_status);
      rsp_ready = 1;
      @(posedge clk); #1;
      rsp_ready = 0;
    end
  endtask

  task automatic issue_commit;
    integer guard;
    begin
      @(negedge clk);
      prune_cmd_opcode = 3'd2;
      prune_cmd_id = 16'd9;
      prune_cmd_valid = 1;
      #1;
      guard = 0;
      while (!prune_cmd_ready) begin
        @(negedge clk);
        guard = guard + 1;
        if (guard > 30) $fatal(1,
          "prune_cmd_ready timeout valid=%0d rsp_valid=%0d pending=%0d protocol=%0d sticky=%0d mode=%0d",
          prune_cmd_valid, rsp_valid, pending_valid, protocol_error,
          prune_sticky_halt_state, mode_state);
      end
      @(posedge clk); #1;
      prune_cmd_valid = 0;
      guard = 0;
      while (!prune_rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 60) $fatal(1, "commit response timeout");
      end
      if (prune_rsp_status != 0 || prune_rsp_id != 16'd9
          || prune_rsp_mask != 4'b0011)
        $fatal(1, "commit response mismatch status=%0d id=%0d mask=%b",
          prune_rsp_status, prune_rsp_id, prune_rsp_mask);
      if (!prune_mask_valid_state || prune_structural_mask_state != 4'b0011)
        $fatal(1, "committed mask not visible with response");
    end
  endtask

  initial begin
    repeat (3) @(posedge clk);
    rst = 0;

    // 形成可检测的动态历史，并证明 STATE_CLEAR 不得改权重。
    issue_core(5, 0, 3, 0);
    issue_core(0, 1, 0, 0);
    issue_core(2, 1, 0, 0);
    if (weight0 != 3 || soma_state != 3 || pre_age_flat[3:0] == 0
        || leak_timer_state == 0)
      $fatal(1, "directed setup did not create dynamic history");

    issue_commit();
    if ({auto_clear_bit}) begin
      if (soma_state != 0 || refractory_state != 0 || leak_timer_state != 0
          || pre_age_flat != 0 || post_age_state != 0
          || positive_evidence != 0 || negative_evidence != 0
          || captured_direction_flat != 0 || pending_valid)
        $fatal(1, "default commit response preceded STATE_CLEAR completion");
    end else begin
      if (soma_state != 3 || pre_age_flat[3:0] == 0 || leak_timer_state == 0)
        $fatal(1, "AUTO_CLEAR_ON_COMMIT=0 cleared history before barrier");
    end
    if (weight0 != 3 || prune_utility_state != 0)
      $fatal(1, "commit clear changed persistent model state");

    prune_rsp_ready = 1;
    @(posedge clk); #1;
    prune_rsp_ready = 0;

    if (!{auto_clear_bit}) begin
      issue_core(1, 0, 0, 0);
      if (soma_state != 0 || refractory_state != 0 || leak_timer_state != 0
          || pre_age_flat != 0 || post_age_state != 0
          || positive_evidence != 0 || negative_evidence != 0
          || captured_direction_flat != 0 || pending_valid)
        $fatal(1, "network-managed STATE_CLEAR did not clear history");
      if (weight0 != 3 || !prune_mask_valid_state
          || prune_structural_mask_state != 4'b0011 || prune_utility_state != 0)
        $fatal(1, "network-managed STATE_CLEAR changed persistent state");
    end

    if (prune_sticky_halt_state)
      $fatal(1, "unexpected sticky halt");
    $display("AUTO_CLEAR_CONTRACT_PASS module={module_name} auto={auto_clear_bit}");
    $finish;
  end
endmodule
"""


def run_auto_clear_contract() -> None:
    """验证单核自动 clear 与网络 barrier 管理 clear 两种部署合同。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    sources = (
        ROOT / "local_prune_gate_2of4.sv",
        ROOT / "local_prune_evidence_gain.sv",
        ROOT / "pulse_mini_prune_bridge.sv",
        ROOT / "pulse_mini_core.sv",
        ROOT / "pulse_mini_l2_core.sv",
        ROOT / "pulse_mini_l_prune_wrapper.sv",
        ROOT / "pulse_mini_l2_prune_wrapper.sv",
    )
    with tempfile.TemporaryDirectory(prefix="pulse_prune_auto_clear_") as temp:
        temp_path = Path(temp)
        for module_name, l2 in (
            ("pulse_mini_l_prune_wrapper", False),
            ("pulse_mini_l2_prune_wrapper", True),
        ):
            for auto_clear in (True, False):
                suffix = "auto" if auto_clear else "barrier"
                tb_path = temp_path / f"tb_{module_name}_{suffix}.sv"
                sim_path = temp_path / f"{module_name}_{suffix}.vvp"
                tb_path.write_text(
                    _auto_clear_contract_tb(
                        module_name, l2=l2, auto_clear=auto_clear
                    ),
                    encoding="utf-8",
                )
                compile_result = subprocess.run(
                    [str(iverilog), "-g2012", "-Wall", "-s", "tb", "-o", str(sim_path),
                     *(str(path) for path in sources), str(tb_path)],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                if compile_result.returncode:
                    raise RuntimeError(compile_result.stdout + compile_result.stderr)
                run = subprocess.run(
                    [str(vvp), str(sim_path)], cwd=ROOT,
                    capture_output=True, text=True, check=False,
                )
                if run.returncode or "AUTO_CLEAR_CONTRACT_PASS" not in run.stdout:
                    raise RuntimeError(run.stdout + run.stderr)


def _tick_gate_contract_tb(module_name: str, *, l2: bool) -> str:
    evidence_width = 8 if l2 else 4
    direction_width = 12 if l2 else 8
    return f"""`timescale 1ns/1ps
module tb;
  logic clk = 0;
  logic rst = 1;
  logic cmd_valid = 0;
  logic cmd_ready;
  logic [2:0] cmd_opcode = 0;
  logic [7:0] cmd_arg0 = 0;
  logic [7:0] cmd_arg1 = 0;
  logic rsp_valid;
  logic rsp_ready = 0;
  logic [2:0] rsp_status;
  logic signed [7:0] rsp_data;
  logic spike;
  logic prune_cmd_valid = 0;
  logic prune_cmd_ready;
  logic [2:0] prune_cmd_opcode = 0;
  logic [15:0] prune_cmd_id = 0;
  logic prune_rsp_valid;
  logic prune_rsp_ready = 0;
  logic [2:0] prune_rsp_status;
  logic [15:0] prune_rsp_id;
  logic [3:0] prune_rsp_mask;
  logic pending_valid;
  logic protocol_error;
  logic [1:0] mode_state;
  logic signed [3:0] weight0, weight1, weight2, weight3;
  logic signed [7:0] soma_state;
  logic [3:0] refractory_state, leak_timer_state;
  logic [15:0] pre_age_flat;
  logic [3:0] post_age_state;
  logic [{evidence_width - 1}:0] positive_evidence, negative_evidence;
  logic signed [{direction_width - 1}:0] captured_direction_flat;
  logic [15:0] prune_utility_state;
  logic [3:0] prune_structural_mask_state;
  logic prune_mask_valid_state;
  logic [31:0] prune_observe_count_state;
  logic [31:0] prune_refractory_skips_state;
  logic prune_sticky_halt_state;
  logic [7:0] prune_latched_evidence_state;
  logic [31:0] prune_dense_reads_state;
  logic [31:0] prune_reads_issued_state;
  logic [31:0] prune_reads_saved_state;
  integer dense_before_refractory;
  integer issued_before_refractory;
  integer saved_before_refractory;

  {module_name} dut (.*);
  always #5 clk = ~clk;

  task automatic issue_core(
      input integer op, input integer a0, input integer a1,
      input integer expected_status);
    integer guard;
    begin
      @(negedge clk);
      guard = 0;
      while (!cmd_ready) begin
        @(negedge clk);
        guard = guard + 1;
        if (guard > 30) $fatal(1, "cmd_ready timeout op=%0d", op);
      end
      cmd_opcode = op[2:0];
      cmd_arg0 = a0[7:0];
      cmd_arg1 = a1[7:0];
      cmd_valid = 1;
      @(posedge clk); #1;
      cmd_valid = 0;
      guard = 0;
      while (!rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 40) $fatal(1, "response timeout op=%0d", op);
      end
      if (rsp_status != expected_status)
        $fatal(1, "status mismatch op=%0d got=%0d expected=%0d",
          op, rsp_status, expected_status);
      rsp_ready = 1;
      @(posedge clk); #1;
      rsp_ready = 0;
    end
  endtask

  task automatic issue_commit;
    integer guard;
    begin
      @(negedge clk);
      prune_cmd_opcode = 3'd2;
      prune_cmd_id = 16'd4;
      prune_cmd_valid = 1;
      #1;
      guard = 0;
      while (!prune_cmd_ready) begin
        @(negedge clk); #1;
        guard = guard + 1;
        if (guard > 30) $fatal(1, "prune_cmd_ready timeout");
      end
      @(posedge clk); #1;
      prune_cmd_valid = 0;
      guard = 0;
      while (!prune_rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 60) $fatal(1, "commit response timeout");
      end
      if (prune_rsp_status != 0 || prune_rsp_mask != 4'b0011)
        $fatal(1, "commit response mismatch status=%0d mask=%b",
          prune_rsp_status, prune_rsp_mask);
      prune_rsp_ready = 1;
      @(posedge clk); #1;
      prune_rsp_ready = 0;
    end
  endtask

  initial begin
    repeat (3) @(posedge clk);
    rst = 0;

    // 四路相同权重使稠密/结构门控后的胞体值可直接观察。
    issue_core(5, 0, 3, 0);
    issue_core(5, 1, 3, 0);
    issue_core(5, 2, 3, 0);
    issue_core(5, 3, 3, 0);
    issue_core(0, 1, 0, 0);

    // mask_valid=0 时必须等价于稠密四路读取；总和 12 触发 spike。
    issue_core(2, 15, 0, 0);
    if (!spike || refractory_state != 1)
      $fatal(1, "dense bypass tick did not reach unmasked core");
    if (prune_dense_reads_state != 4 || prune_reads_issued_state != 4
        || prune_reads_saved_state != 0)
      $fatal(1, "dense bypass accounting mismatch dense=%0d issued=%0d saved=%0d",
        prune_dense_reads_state, prune_reads_issued_state, prune_reads_saved_state);

    // 清理不应期后提交固定 tie-break mask 0011。
    issue_core(1, 0, 0, 0);
    issue_commit();
    if (!prune_mask_valid_state || prune_structural_mask_state != 4'b0011)
      $fatal(1, "mask commit not visible");

    // 同一输入只允许 mask 中两路进入核心；两路各 3，恰好触发 spike。
    issue_core(2, 15, 0, 0);
    if (!spike || refractory_state != 1)
      $fatal(1, "structural mask was not applied before core TICK");
    if (prune_dense_reads_state != 8 || prune_reads_issued_state != 6
        || prune_reads_saved_state != 2)
      $fatal(1, "masked accounting mismatch dense=%0d issued=%0d saved=%0d",
        prune_dense_reads_state, prune_reads_issued_state, prune_reads_saved_state);

    dense_before_refractory = prune_dense_reads_state;
    issued_before_refractory = prune_reads_issued_state;
    saved_before_refractory = prune_reads_saved_state;
    issue_core(2, 15, 0, 0);
    if (prune_refractory_skips_state != 1)
      $fatal(1, "refractory skip not counted separately");
    if (prune_dense_reads_state != dense_before_refractory
        || prune_reads_issued_state != issued_before_refractory
        || prune_reads_saved_state != saved_before_refractory)
      $fatal(1, "refractory skip was misreported as structural work");

    if (prune_sticky_halt_state)
      $fatal(1, "unexpected sticky halt");
    $display("TICK_GATE_CONTRACT_PASS module={module_name}");
    $finish;
  end
endmodule
"""


def run_tick_gate_contract() -> None:
    """验证 TICK 前门控、稠密旁路和不应期独立分账。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    sources = (
        ROOT / "local_prune_gate_2of4.sv",
        ROOT / "local_prune_evidence_gain.sv",
        ROOT / "pulse_mini_prune_bridge.sv",
        ROOT / "pulse_mini_core.sv",
        ROOT / "pulse_mini_l2_core.sv",
        ROOT / "pulse_mini_l_prune_wrapper.sv",
        ROOT / "pulse_mini_l2_prune_wrapper.sv",
    )
    with tempfile.TemporaryDirectory(prefix="pulse_prune_tick_gate_") as temp:
        temp_path = Path(temp)
        for module_name, l2 in (
            ("pulse_mini_l_prune_wrapper", False),
            ("pulse_mini_l2_prune_wrapper", True),
        ):
            tb_path = temp_path / f"tb_{module_name}.sv"
            sim_path = temp_path / f"{module_name}.vvp"
            tb_path.write_text(
                _tick_gate_contract_tb(module_name, l2=l2), encoding="utf-8"
            )
            compile_result = subprocess.run(
                [str(iverilog), "-g2012", "-Wall", "-s", "tb", "-o", str(sim_path),
                 *(str(path) for path in sources), str(tb_path)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            if compile_result.returncode:
                raise RuntimeError(compile_result.stdout + compile_result.stderr)
            run = subprocess.run(
                [str(vvp), str(sim_path)], cwd=ROOT,
                capture_output=True, text=True, check=False,
            )
            if run.returncode or "TICK_GATE_CONTRACT_PASS" not in run.stdout:
                raise RuntimeError(run.stdout + run.stderr)


def _bypass_bit_exact_tb(module_name: str, core_name: str, *, l2: bool) -> str:
    evidence_width = 8 if l2 else 4
    direction_width = 12 if l2 else 8
    return f"""`timescale 1ns/1ps
module tb;
  logic clk = 0;
  logic rst = 1;
  logic cmd_valid = 0;
  logic wrapper_cmd_ready;
  logic bare_cmd_ready;
  logic [2:0] cmd_opcode = 0;
  logic [7:0] cmd_arg0 = 0;
  logic [7:0] cmd_arg1 = 0;
  logic wrapper_rsp_valid;
  logic bare_rsp_valid;
  logic wrapper_rsp_ready = 0;
  logic bare_rsp_ready = 0;
  logic [2:0] wrapper_rsp_status;
  logic [2:0] bare_rsp_status;
  logic signed [7:0] wrapper_rsp_data;
  logic signed [7:0] bare_rsp_data;
  logic wrapper_spike;
  logic bare_spike;
  logic prune_cmd_valid = 0;
  logic prune_cmd_ready;
  logic [2:0] prune_cmd_opcode = 0;
  logic [15:0] prune_cmd_id = 0;
  logic prune_rsp_valid;
  logic prune_rsp_ready = 0;
  logic [2:0] prune_rsp_status;
  logic [15:0] prune_rsp_id;
  logic [3:0] prune_rsp_mask;
  logic wrapper_pending;
  logic bare_pending;
  logic wrapper_protocol_error;
  logic bare_protocol_error;
  logic [1:0] wrapper_mode;
  logic [1:0] bare_mode;
  logic signed [3:0] wrapper_weight0, wrapper_weight1, wrapper_weight2, wrapper_weight3;
  logic signed [3:0] bare_weight0, bare_weight1, bare_weight2, bare_weight3;
  logic signed [7:0] wrapper_soma;
  logic signed [7:0] bare_soma;
  logic [3:0] wrapper_refractory, wrapper_leak_timer;
  logic [3:0] bare_refractory, bare_leak_timer;
  logic [15:0] wrapper_pre_age_flat;
  logic [15:0] bare_pre_age_flat;
  logic [3:0] wrapper_post_age;
  logic [3:0] bare_post_age;
  logic [{evidence_width - 1}:0] wrapper_positive_evidence, wrapper_negative_evidence;
  logic [{evidence_width - 1}:0] bare_positive_evidence, bare_negative_evidence;
  logic signed [{direction_width - 1}:0] wrapper_captured_direction_flat;
  logic signed [{direction_width - 1}:0] bare_captured_direction_flat;
  logic [15:0] prune_utility_state;
  logic [3:0] prune_structural_mask_state;
  logic prune_mask_valid_state;
  logic [31:0] prune_observe_count_state;
  logic [31:0] prune_refractory_skips_state;
  logic prune_sticky_halt_state;
  logic [7:0] prune_latched_evidence_state;
  logic [31:0] prune_dense_reads_state;
  logic [31:0] prune_reads_issued_state;
  logic [31:0] prune_reads_saved_state;

  {module_name} wrapper (
    .clk(clk), .rst(rst),
    .cmd_valid(cmd_valid), .cmd_ready(wrapper_cmd_ready),
    .cmd_opcode(cmd_opcode), .cmd_arg0(cmd_arg0), .cmd_arg1(cmd_arg1),
    .rsp_valid(wrapper_rsp_valid), .rsp_ready(wrapper_rsp_ready),
    .rsp_status(wrapper_rsp_status), .rsp_data(wrapper_rsp_data), .spike(wrapper_spike),
    .prune_cmd_valid(prune_cmd_valid), .prune_cmd_ready(prune_cmd_ready),
    .prune_cmd_opcode(prune_cmd_opcode), .prune_cmd_id(prune_cmd_id),
    .prune_rsp_valid(prune_rsp_valid), .prune_rsp_ready(prune_rsp_ready),
    .prune_rsp_status(prune_rsp_status), .prune_rsp_id(prune_rsp_id),
    .prune_rsp_mask(prune_rsp_mask),
    .pending_valid(wrapper_pending), .protocol_error(wrapper_protocol_error),
    .mode_state(wrapper_mode),
    .weight0(wrapper_weight0), .weight1(wrapper_weight1),
    .weight2(wrapper_weight2), .weight3(wrapper_weight3),
    .soma_state(wrapper_soma), .refractory_state(wrapper_refractory),
    .leak_timer_state(wrapper_leak_timer), .pre_age_flat(wrapper_pre_age_flat),
    .post_age_state(wrapper_post_age),
    .positive_evidence(wrapper_positive_evidence),
    .negative_evidence(wrapper_negative_evidence),
    .captured_direction_flat(wrapper_captured_direction_flat),
    .prune_utility_state(prune_utility_state),
    .prune_structural_mask_state(prune_structural_mask_state),
    .prune_mask_valid_state(prune_mask_valid_state),
    .prune_observe_count_state(prune_observe_count_state),
    .prune_refractory_skips_state(prune_refractory_skips_state),
    .prune_sticky_halt_state(prune_sticky_halt_state),
    .prune_latched_evidence_state(prune_latched_evidence_state),
    .prune_dense_reads_state(prune_dense_reads_state),
    .prune_reads_issued_state(prune_reads_issued_state),
    .prune_reads_saved_state(prune_reads_saved_state)
  );

  {core_name} bare (
    .clk(clk), .rst(rst),
    .cmd_valid(cmd_valid), .cmd_ready(bare_cmd_ready),
    .cmd_opcode(cmd_opcode), .cmd_arg0(cmd_arg0), .cmd_arg1(cmd_arg1),
    .rsp_valid(bare_rsp_valid), .rsp_ready(bare_rsp_ready),
    .rsp_status(bare_rsp_status), .rsp_data(bare_rsp_data), .spike(bare_spike),
    .pending_valid(bare_pending), .protocol_error(bare_protocol_error),
    .mode_state(bare_mode),
    .weight0(bare_weight0), .weight1(bare_weight1),
    .weight2(bare_weight2), .weight3(bare_weight3),
    .soma_state(bare_soma), .refractory_state(bare_refractory),
    .leak_timer_state(bare_leak_timer), .pre_age_flat(bare_pre_age_flat),
    .post_age_state(bare_post_age),
    .positive_evidence(bare_positive_evidence),
    .negative_evidence(bare_negative_evidence),
    .captured_direction_flat(bare_captured_direction_flat)
  );

  always #5 clk = ~clk;

  task automatic compare_public_state(input integer op);
    begin
      if (wrapper_rsp_status !== bare_rsp_status
          || wrapper_rsp_data !== bare_rsp_data
          || wrapper_spike !== bare_spike)
        $fatal(1, "response mismatch op=%0d", op);
      if (wrapper_pending !== bare_pending
          || wrapper_protocol_error !== bare_protocol_error
          || wrapper_mode !== bare_mode
          || wrapper_weight0 !== bare_weight0 || wrapper_weight1 !== bare_weight1
          || wrapper_weight2 !== bare_weight2 || wrapper_weight3 !== bare_weight3
          || wrapper_soma !== bare_soma
          || wrapper_refractory !== bare_refractory
          || wrapper_leak_timer !== bare_leak_timer
          || wrapper_pre_age_flat !== bare_pre_age_flat
          || wrapper_post_age !== bare_post_age
          || wrapper_positive_evidence !== bare_positive_evidence
          || wrapper_negative_evidence !== bare_negative_evidence
          || wrapper_captured_direction_flat !== bare_captured_direction_flat)
        $fatal(1, "core state mismatch op=%0d", op);
      if (prune_mask_valid_state || prune_structural_mask_state != 4'b1111)
        $fatal(1, "uncommitted bypass unexpectedly changed structural mask");
    end
  endtask

  task automatic issue_both(
      input integer op, input integer a0, input integer a1);
    integer guard;
    begin
      @(negedge clk);
      guard = 0;
      while (!wrapper_cmd_ready || !bare_cmd_ready) begin
        @(negedge clk);
        guard = guard + 1;
        if (guard > 40) $fatal(1, "joint command ready timeout op=%0d", op);
      end
      cmd_opcode = op[2:0];
      cmd_arg0 = a0[7:0];
      cmd_arg1 = a1[7:0];
      cmd_valid = 1;
      @(posedge clk); #1;
      cmd_valid = 0;
      guard = 0;
      while (!wrapper_rsp_valid || !bare_rsp_valid) begin
        @(posedge clk); #1;
        guard = guard + 1;
        if (guard > 60) $fatal(1, "joint response timeout op=%0d", op);
      end
      compare_public_state(op);
      wrapper_rsp_ready = 1;
      bare_rsp_ready = 1;
      @(posedge clk); #1;
      wrapper_rsp_ready = 0;
      bare_rsp_ready = 0;
    end
  endtask

  initial begin
    repeat (3) @(posedge clk);
    rst = 0;

    issue_both(5, 0, 2);
    issue_both(5, 1, 15);
    issue_both(5, 2, 1);
    issue_both(0, 1, 0);
    issue_both(2, 3, 1);
    issue_both(3, 0, 0);
    issue_both(4, 1, 0);
    issue_both(1, 0, 0);
    issue_both(4, 1, 0);
    issue_both(2, 16, 0);
    issue_both(0, 2, 0);
    issue_both(2, 5, 0);
    issue_both(6, 0, 0);

    if (prune_observe_count_state != 1 || prune_sticky_halt_state)
      $fatal(1, "bypass audit state mismatch");
    $display("BYPASS_BIT_EXACT_PASS module={module_name}");
    $finish;
  end
endmodule
"""


def run_bypass_bit_exact_contract() -> None:
    """在 mask 未提交时逐事务比较 wrapper 与裸核心公开状态。"""

    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    sources = (
        ROOT / "local_prune_gate_2of4.sv",
        ROOT / "local_prune_evidence_gain.sv",
        ROOT / "pulse_mini_prune_bridge.sv",
        ROOT / "pulse_mini_core.sv",
        ROOT / "pulse_mini_l2_core.sv",
        ROOT / "pulse_mini_l_prune_wrapper.sv",
        ROOT / "pulse_mini_l2_prune_wrapper.sv",
    )
    with tempfile.TemporaryDirectory(prefix="pulse_prune_bypass_") as temp:
        temp_path = Path(temp)
        for module_name, core_name, l2 in (
            ("pulse_mini_l_prune_wrapper", "pulse_mini_core", False),
            ("pulse_mini_l2_prune_wrapper", "pulse_mini_l2_core", True),
        ):
            tb_path = temp_path / f"tb_{module_name}.sv"
            sim_path = temp_path / f"{module_name}.vvp"
            tb_path.write_text(
                _bypass_bit_exact_tb(module_name, core_name, l2=l2),
                encoding="utf-8",
            )
            compile_result = subprocess.run(
                [str(iverilog), "-g2012", "-Wall", "-s", "tb", "-o", str(sim_path),
                 *(str(path) for path in sources), str(tb_path)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            if compile_result.returncode:
                raise RuntimeError(compile_result.stdout + compile_result.stderr)
            run = subprocess.run(
                [str(vvp), str(sim_path)], cwd=ROOT,
                capture_output=True, text=True, check=False,
            )
            if run.returncode or "BYPASS_BIT_EXACT_PASS" not in run.stdout:
                raise RuntimeError(run.stdout + run.stderr)


__all__ = [
    "compile_public_interfaces",
    "run_auto_clear_contract",
    "run_bypass_bit_exact_contract",
    "run_feedback_contract",
    "run_tick_gate_contract",
]

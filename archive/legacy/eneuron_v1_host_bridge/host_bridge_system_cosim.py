"""完整 Host Bridge 系统的非整数双时钟 Icarus/Python 协同仿真。"""

from __future__ import annotations

import logging
import os
import random
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from host_bridge_controller_cosim import command, random_commands
from host_bridge_oracle import Flit, HostBridgeOracle, Opcode, Status
from rtl_tile_cosim import find_tool


LOGGER = logging.getLogger("host_bridge_system_cosim")
ROOT = Path(__file__).resolve().parent


def expected_responses(commands: tuple[Flit, ...]) -> tuple[Flit, ...]:
    """按 response FIFO 接受边界执行事务级 oracle。"""
    bridge = HostBridgeOracle()
    return tuple(bridge.execute(request) for request in commands)


def clock_parameters(seed: int) -> tuple[int, int, int, int]:
    """生成非整数频比和非零初始相位，单位为 ps。"""
    rng = random.Random(seed ^ 0xD04C)
    host_half = rng.choice((9_500, 10_000, 10_500, 11_000))
    tile_half = rng.choice((5_500, 6_000, 6_500, 7_000))
    if host_half % tile_half == 0 or tile_half % host_half == 0:
        tile_half += 250
    return host_half, tile_half, rng.randrange(1, host_half), rng.randrange(1, tile_half)


def system_declarations(host_half: int, tile_half: int, host_phase: int, tile_phase: int) -> str:
    """生成系统顶层实例、时钟和公共协议监视器。"""
    return f"""
  localparam integer HOST_HALF={host_half};
  localparam integer TILE_HALF={tile_half};
  localparam integer HOST_PHASE={host_phase};
  localparam integer TILE_PHASE={tile_phase};

  logic host_clk=1'b0, tile_clk=1'b0, bridge_rst=1'b1;
  logic host_cmd_valid=1'b0; wire host_cmd_ready; logic [127:0] host_cmd_data='0;
  wire host_rsp_valid; logic host_rsp_ready=1'b0; wire [127:0] host_rsp_data;
  wire status_irq;
  wire debug_host_rst, debug_tile_rst, debug_tile_domain_up;
  wire [3:0] debug_fifo_rst_busy;
  wire debug_tile_ready, debug_tile_busy, debug_tile_protocol_error;
  wire [1:0] debug_tile_output_spikes;

  initial begin #HOST_PHASE; forever #HOST_HALF host_clk=~host_clk; end
  initial begin #TILE_PHASE; forever #TILE_HALF tile_clk=~tile_clk; end

  digital_snn_host_bridge_system dut (.*);

  logic host_cmd_stalled=1'b0, host_rsp_stalled=1'b0;
  logic [127:0] held_cmd='0, held_rsp='0;
  integer saw_cmd_backpressure=0, saw_rsp_backpressure=0;

  always @(posedge host_clk) begin
    if (status_irq !== host_rsp_valid) $fatal(1, "status_irq mismatch");
    if ((debug_host_rst || debug_fifo_rst_busy[0]) && host_cmd_ready)
      $fatal(1, "command ready leaked during reset busy");
    if ((debug_host_rst || debug_fifo_rst_busy[3]) && host_rsp_valid)
      $fatal(1, "response valid leaked during reset busy");

    if (host_cmd_valid && !host_cmd_ready) begin
      saw_cmd_backpressure=1;
      if (host_cmd_stalled && host_cmd_data !== held_cmd)
        $fatal(1, "host command changed while stalled");
      held_cmd=host_cmd_data; host_cmd_stalled=1'b1;
    end else host_cmd_stalled=1'b0;

    if (host_rsp_valid && !host_rsp_ready) begin
      saw_rsp_backpressure=1;
      if (host_rsp_stalled && host_rsp_data !== held_rsp)
        $fatal(1, "host response changed while stalled");
      held_rsp=host_rsp_data; host_rsp_stalled=1'b1;
    end else host_rsp_stalled=1'b0;
  end

  always @(posedge tile_clk) begin
    if (debug_tile_protocol_error)
      $fatal(1, "controller allowed an unexpected Tile protocol error");
  end
"""


def make_random_testbench(
    command_count: int,
    host_half: int,
    tile_half: int,
    host_phase: int,
    tile_phase: int,
) -> str:
    """生成并发 producer/consumer 双时钟端到端 testbench。"""
    declarations = system_declarations(host_half, tile_half, host_phase, tile_phase)
    return f"""`timescale 1ps/1ps
module tb;
{declarations}
  localparam integer COMMAND_COUNT={command_count};
  integer command_file, response_file, scan_result;
  integer producer_index, consumer_index, command_gap, response_gap;
  integer accepted_commands=0, accepted_responses=0;
  logic [127:0] command_word, expected_response;

  initial begin
    command_file=$fopen("commands.txt", "r");
    response_file=$fopen("responses.txt", "r");
    if (!command_file || !response_file) $fatal(1, "cannot open vector files");

    repeat(10) @(posedge host_clk); #1 bridge_rst=1'b0;
    wait(host_cmd_ready && debug_tile_domain_up && debug_fifo_rst_busy==0);

    fork
      begin : producer
        for (producer_index=0; producer_index<COMMAND_COUNT; producer_index=producer_index+1) begin
          scan_result=$fscanf(command_file, "%h %d\\n", command_word, command_gap);
          if (scan_result != 2) $fatal(1, "bad command vector %0d", producer_index);
          repeat(command_gap) @(posedge host_clk);
          @(negedge host_clk); host_cmd_data=command_word; host_cmd_valid=1'b1;
          do @(posedge host_clk); while(!host_cmd_ready);
          accepted_commands=accepted_commands+1;
          @(negedge host_clk); host_cmd_valid=1'b0;
        end
      end
      begin : consumer
        // Force response FIFO saturation before entering random backpressure.
        repeat(300) @(posedge host_clk);
        for (consumer_index=0; consumer_index<COMMAND_COUNT; consumer_index=consumer_index+1) begin
          scan_result=$fscanf(response_file, "%h %d\\n", expected_response, response_gap);
          if (scan_result != 2) $fatal(1, "bad response vector %0d", consumer_index);
          repeat(response_gap) @(posedge host_clk);
          @(negedge host_clk); host_rsp_ready=1'b1;
          do @(posedge host_clk); while(!host_rsp_valid);
          if (host_rsp_data !== expected_response)
            $fatal(1, "response[%0d] actual=%032h expected=%032h",
              consumer_index, host_rsp_data, expected_response);
          accepted_responses=accepted_responses+1;
          @(negedge host_clk); host_rsp_ready=1'b0;
        end
      end
    join

    repeat(20) @(posedge host_clk);
    if (accepted_commands != COMMAND_COUNT || accepted_responses != COMMAND_COUNT)
      $fatal(1, "transaction count mismatch cmd=%0d rsp=%0d",
        accepted_commands, accepted_responses);
    if (!saw_cmd_backpressure) $fatal(1, "command FIFO backpressure not covered");
    if (!saw_rsp_backpressure) $fatal(1, "response backpressure not covered");
    if (host_rsp_valid) $fatal(1, "response FIFO not empty at completion");
    $display("SYSTEM_RANDOM_PASS commands=%0d host_half=%0d tile_half=%0d",
      COMMAND_COUNT, HOST_HALF, TILE_HALF);
    $finish;
  end

  initial begin #2000000000; $fatal(1, "random system timeout"); end
endmodule
"""


def make_sequence_testbench(
    command_count: int,
    host_half: int,
    tile_half: int,
    host_phase: int,
    tile_phase: int,
) -> str:
    """生成给定命令序列的双时钟端到端 testbench。"""
    declarations = system_declarations(host_half, tile_half, host_phase, tile_phase)
    return f"""`timescale 1ps/1ps
module tb;
{declarations}
  localparam integer COMMAND_COUNT={command_count};
  integer command_file, response_gap_file, scan_result;
  integer producer_index, consumer_index, command_gap, response_gap;
  integer accepted_commands=0, accepted_responses=0;
  logic [127:0] command_word;

  initial begin
    command_file=$fopen("commands.txt", "r");
    response_gap_file=$fopen("response_gaps.txt", "r");
    if (!command_file || !response_gap_file) $fatal(1, "cannot open sequence files");

    // 第一条命令跨 reset-busy 保持 valid，保证命令侧背压路径被真实覆盖。
    scan_result=$fscanf(command_file, "%h %d\\n", command_word, command_gap);
    if (scan_result != 2) $fatal(1, "bad command vector 0");
    @(negedge host_clk); host_cmd_data=command_word; host_cmd_valid=1'b1;
    repeat(10) @(posedge host_clk); #1 bridge_rst=1'b0;
    do @(posedge host_clk); while(!host_cmd_ready);
    accepted_commands=1;
    @(negedge host_clk); host_cmd_valid=1'b0;
    wait(debug_tile_domain_up && debug_fifo_rst_busy==0);

    fork
      begin : producer
        for (producer_index=1; producer_index<COMMAND_COUNT; producer_index=producer_index+1) begin
          scan_result=$fscanf(command_file, "%h %d\\n", command_word, command_gap);
          if (scan_result != 2) $fatal(1, "bad command vector %0d", producer_index);
          repeat(command_gap) @(posedge host_clk);
          @(negedge host_clk); host_cmd_data=command_word; host_cmd_valid=1'b1;
          do @(posedge host_clk); while(!host_cmd_ready);
          accepted_commands=accepted_commands+1;
          @(negedge host_clk); host_cmd_valid=1'b0;
        end
      end
      begin : consumer
        // 先阻塞响应端，使响应 FIFO 和 valid 稳定性监视器进入背压状态。
        repeat(300) @(posedge host_clk);
        for (consumer_index=0; consumer_index<COMMAND_COUNT; consumer_index=consumer_index+1) begin
          scan_result=$fscanf(response_gap_file, "%d\\n", response_gap);
          if (scan_result != 1) $fatal(1, "bad response gap %0d", consumer_index);
          repeat(response_gap) @(posedge host_clk);
          @(negedge host_clk); host_rsp_ready=1'b1;
          do @(posedge host_clk); while(!host_rsp_valid);
          $display("SEQUENCE_RESPONSE %0d %032h", consumer_index, host_rsp_data);
          accepted_responses=accepted_responses+1;
          @(negedge host_clk); host_rsp_ready=1'b0;
        end
      end
    join

    repeat(20) @(posedge host_clk);
    if (accepted_commands != COMMAND_COUNT || accepted_responses != COMMAND_COUNT)
      $fatal(1, "sequence count mismatch cmd=%0d rsp=%0d",
        accepted_commands, accepted_responses);
    if (!saw_cmd_backpressure) $fatal(1, "sequence command backpressure not covered");
    if (!saw_rsp_backpressure) $fatal(1, "sequence response backpressure not covered");
    if (host_rsp_valid) $fatal(1, "sequence response FIFO not empty");
    $display("SYSTEM_SEQUENCE_PASS commands=%0d host_half=%0d tile_half=%0d",
      COMMAND_COUNT, HOST_HALF, TILE_HALF);
    $finish;
  end

  initial begin #500000000; $fatal(1, "sequence system timeout"); end
endmodule
"""


def make_reset_testbench(host_half: int, tile_half: int, host_phase: int, tile_phase: int) -> str:
    """生成 hard reset 丢弃 ledger、清权重的固定 testbench。"""
    declarations = system_declarations(host_half, tile_half, host_phase, tile_phase)
    write = command(Opcode.WEIGHT_WRITE, txn_id=1, arg0=9 << 4).pack()
    read_before = command(Opcode.WEIGHT_READ, txn_id=2, arg0=0).pack()
    reset_oracle = HostBridgeOracle()
    reset_oracle.execute(command(Opcode.WEIGHT_WRITE, txn_id=1, arg0=9 << 4))
    expected_before = reset_oracle.execute(
        command(Opcode.WEIGHT_READ, txn_id=2, arg0=0)
    ).pack()
    read_after = command(Opcode.WEIGHT_READ, txn_id=0x100, arg0=0).pack()
    expected_after = Flit(
        Opcode.WEIGHT_READ, Status.OK, 0x100, 0, 0, 2, 0
    ).pack()
    status_command = command(Opcode.STATUS_READ, txn_id=0x200).pack()
    return f"""`timescale 1ps/1ps
module tb;
{declarations}
  integer i, outstanding_sent=0;

  task automatic send_command(input logic [127:0] value); begin
    @(negedge host_clk); host_cmd_data=value; host_cmd_valid=1'b1;
    do @(posedge host_clk); while(!host_cmd_ready);
    @(negedge host_clk); host_cmd_valid=1'b0;
  end endtask

  task automatic receive_response(input logic [127:0] expected); begin
    @(negedge host_clk); host_rsp_ready=1'b1;
    do @(posedge host_clk); while(!host_rsp_valid);
    if (host_rsp_data !== expected)
      $fatal(1, "reset regression response actual=%032h expected=%032h",
        host_rsp_data, expected);
    @(negedge host_clk); host_rsp_ready=1'b0;
  end endtask

  initial begin
    repeat(10) @(posedge host_clk); #1 bridge_rst=1'b0;
    wait(host_cmd_ready && debug_tile_domain_up && debug_fifo_rst_busy==0);

    send_command(128'h{write:032x});
    receive_response(128'h{HostBridgeOracle().execute(command(Opcode.WEIGHT_WRITE, txn_id=1, arg0=9 << 4)).pack():032x});
    send_command(128'h{read_before:032x});
    receive_response(128'h{expected_before:032x});

    // Keep Host responses blocked while commands and responses become outstanding.
    host_rsp_ready=1'b0;
    for (i=0; i<12; i=i+1) begin
      send_command(128'h{status_command:032x} + (i << 96));
      outstanding_sent=outstanding_sent+1;
    end
    wait(host_rsp_valid);
    wait(!dut.host_bridge.cmd_wr_rst_busy && !dut.host_bridge.rsp_wr_rst_busy);
    #3 bridge_rst=1'b1;
    repeat(12) @(posedge host_clk);
    if (host_cmd_ready || host_rsp_valid)
      $fatal(1, "Host interface active while hard reset asserted");
    #3 bridge_rst=1'b0;
    wait(host_cmd_ready && debug_tile_domain_up && debug_fifo_rst_busy==0);
    repeat(8) @(posedge host_clk);
    if (host_rsp_valid) $fatal(1, "pre-reset response survived hard reset");

    send_command(128'h{read_after:032x});
    receive_response(128'h{expected_after:032x});
    $display("SYSTEM_RESET_PASS discarded=%0d restored_weight=2", outstanding_sent);
    $finish;
  end

  initial begin #500000000; $fatal(1, "reset system timeout"); end
endmodule
"""


def compile_and_run(testbench: str, files: dict[str, str], timeout: int = 120) -> str:
    """用接口等价 async FIFO 模型编译并运行完整系统。"""
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 iverilog 和 vvp")
    with tempfile.TemporaryDirectory(prefix="eneuron_system_") as temp_dir:
        temp = Path(temp_dir)
        tb_path = temp / "tb.sv"
        sim_path = temp / "tb.vvp"
        tb_path.write_text(testbench, encoding="utf-8")
        for name, content in files.items():
            (temp / name).write_text(content, encoding="ascii")
        compile_result = subprocess.run(
            [
                str(iverilog), "-g2012", "-Wall", "-s", "tb", "-o", str(sim_path),
                str(ROOT / "xpm_fifo_async_sim.sv"),
                str(ROOT / "digital_lif_engine.sv"),
                str(ROOT / "digital_snn_tile_4x2x2.sv"),
                str(ROOT / "digital_snn_host_bridge_controller.sv"),
                str(ROOT / "digital_snn_host_bridge.sv"),
                str(ROOT / "digital_snn_host_bridge_system.sv"),
                str(tb_path),
            ],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        if compile_result.returncode != 0:
            raise RuntimeError(
                f"iverilog failed:\n{compile_result.stdout}\n{compile_result.stderr}"
            )
        env = os.environ.copy()
        env["PATH"] = f"{vvp.parent}{os.pathsep}{env.get('PATH', '')}"
        result = subprocess.run(
            [str(vvp), str(sim_path)], cwd=temp, capture_output=True, text=True,
            check=False, env=env, timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"vvp failed:\n{result.stdout}\n{result.stderr}")
        return result.stdout


def run_random_system_cosim(seed: int, command_count: int) -> None:
    """运行一组完整双时钟随机 producer/consumer 流。"""
    commands = random_commands(seed, command_count)
    responses = expected_responses(commands)
    rng = random.Random(seed ^ 0x51A7)
    command_lines = "".join(
        f"{request.pack():032x} {rng.randrange(3)}\n" for request in commands
    )
    response_lines = "".join(
        f"{response.pack():032x} {rng.randrange(6)}\n" for response in responses
    )
    clocks = clock_parameters(seed)
    output = compile_and_run(
        make_random_testbench(command_count, *clocks),
        {"commands.txt": command_lines, "responses.txt": response_lines},
        timeout=180,
    )
    if "SYSTEM_RANDOM_PASS" not in output:
        raise AssertionError(f"随机系统仿真未到达 pass:\n{output}")
    LOGGER.info("system cosim passed: seed=%d commands=%d", seed, command_count)


def run_command_sequence(commands: Sequence[Flit], seed: int) -> tuple[Flit, ...]:
    """在真实双时钟系统中执行给定命令，并返回硬件实际响应。"""
    frozen_commands = tuple(commands)
    if not frozen_commands:
        LOGGER.info("system sequence cosim skipped: seed=%d commands=0", seed)
        return ()

    expected = expected_responses(frozen_commands)
    rng = random.Random(seed ^ 0x5E91)
    command_lines = "".join(
        f"{request.pack():032x} {rng.randrange(3)}\n" for request in frozen_commands
    )
    response_gap_lines = "".join(
        f"{rng.randrange(6)}\n" for _ in frozen_commands
    )
    clocks = clock_parameters(seed)
    LOGGER.info(
        "system sequence cosim started: seed=%d commands=%d clocks=%s",
        seed,
        len(frozen_commands),
        clocks,
    )
    output = compile_and_run(
        make_sequence_testbench(len(frozen_commands), *clocks),
        {
            "commands.txt": command_lines,
            "response_gaps.txt": response_gap_lines,
        },
        timeout=120,
    )
    if "SYSTEM_SEQUENCE_PASS" not in output:
        raise AssertionError(f"命令序列系统仿真未到达 pass:\n{output}")

    actual_by_index: dict[int, Flit] = {}
    for line in output.splitlines():
        if not line.startswith("SEQUENCE_RESPONSE "):
            continue
        marker, index_text, response_text = line.split()
        if marker != "SEQUENCE_RESPONSE":
            continue
        actual_by_index[int(index_text)] = Flit.unpack(int(response_text, 16))

    actual = tuple(
        actual_by_index[index] for index in range(len(frozen_commands))
        if index in actual_by_index
    )
    if len(actual) != len(expected):
        raise AssertionError(
            f"实际响应数量错误: actual={len(actual)} expected={len(expected)}\n{output}"
        )
    for index, (actual_response, expected_response) in enumerate(zip(actual, expected)):
        if actual_response != expected_response:
            LOGGER.error(
                "system sequence response mismatch: seed=%d index=%d actual=%032x expected=%032x",
                seed,
                index,
                actual_response.pack(),
                expected_response.pack(),
            )
            raise AssertionError(
                "响应与 HostBridgeOracle 不一致: "
                f"index={index} actual={actual_response.pack():032x} "
                f"expected={expected_response.pack():032x}"
            )
    LOGGER.info(
        "system sequence cosim passed: seed=%d commands=%d", seed, len(actual)
    )
    return actual


def run_hard_reset_system_regression() -> None:
    """验证 hard reset 的明确破坏性边界。"""
    clocks = clock_parameters(0xA11)
    output = compile_and_run(make_reset_testbench(*clocks), {}, timeout=60)
    if "SYSTEM_RESET_PASS" not in output:
        raise AssertionError(f"hard reset 系统仿真未到达 pass:\n{output}")

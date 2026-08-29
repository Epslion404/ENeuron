"""局部 2:4 剪枝控制器的 Python/Icarus 逐事务协同仿真。"""

from __future__ import annotations

import logging
import os
import random
import re
import subprocess
import tempfile
from pathlib import Path

from local_prune_rtl_reference import (
    GateTransaction,
    LocalPruneRtlReference,
    Mode,
    Opcode,
    pack_levels,
)
from rtl_tile_cosim import find_tool


ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("local_prune_gate_cosim")
ROW_RE = re.compile(r"^ROW\s+" + r"\s+".join([r"(-?\d+)"] * 24) + r"$")
LEGAL_MASKS = (0b0011, 0b0101, 0b0110, 0b1001, 0b1010, 0b1100)
GAIN_MODULES = {
    "eneuron": "eneuron_prune_evidence_gain",
    "pulse_mini_l": "pulse_mini_l_prune_evidence_gain",
    "pulse_mini_l2": "pulse_mini_l2_prune_evidence_gain",
}


def _directed_prefix() -> list[GateTransaction]:
    """固定覆盖 ID、模式、安全边界、原子提交、六种 mask 和分层计数。"""

    transactions = [
        GateTransaction(kind=0, mode=Mode.CONFIG, opcode=Opcode.PRUNE_CLEAR),
        GateTransaction(
            kind=0,
            mode=Mode.TRAIN,
            opcode=Opcode.OBSERVE,
            txn_id=0,
            raw_evidence_flat=pack_levels((3, 2, 1, 0)),
            modulator_nonzero=1,
        ),
        GateTransaction(
            kind=0,
            mode=Mode.TRAIN,
            opcode=Opcode.OBSERVE,
            txn_id=0,
            raw_evidence_flat=pack_levels((3, 3, 3, 3)),
            modulator_nonzero=1,
        ),
        GateTransaction(
            kind=0,
            mode=Mode.INFER,
            opcode=Opcode.OBSERVE,
            txn_id=1,
            raw_evidence_flat=pack_levels((3, 3, 3, 3)),
            modulator_nonzero=1,
        ),
        GateTransaction(
            kind=0,
            mode=Mode.TRAIN,
            opcode=Opcode.OBSERVE,
            txn_id=1,
            raw_evidence_flat=pack_levels((0, 0, 0, 0)),
            modulator_nonzero=0,
            response_hold_cycles=3,
            inject_busy_command=1,
        ),
        GateTransaction(
            kind=0,
            mode=Mode.TRAIN,
            opcode=Opcode.PRUNE_COMMIT,
            txn_id=8,
            core_idle=0,
            pending_snapshot=1,
            pending_mod_commit=1,
        ),
        GateTransaction(
            kind=0,
            mode=Mode.TRAIN,
            opcode=Opcode.PRUNE_COMMIT,
            txn_id=9,
            response_hold_cycles=4,
            inject_busy_command=1,
        ),
        GateTransaction(
            kind=0,
            mode=Mode.TRAIN,
            opcode=Opcode.PRUNE_COMMIT,
            txn_id=10,
        ),
        GateTransaction(kind=0, mode=Mode.INFER, opcode=Opcode.MASK_READ),
        GateTransaction(kind=0, mode=Mode.INFER, opcode=Opcode.PRUNE_CLEAR),
        GateTransaction(kind=0, mode=Mode.INVALID, opcode=Opcode.MASK_READ),
        GateTransaction(kind=0, mode=Mode.CONFIG, opcode=7),
        GateTransaction(kind=2, issue_valid=1, activity_mask=0, issue_layer_output=0),
        GateTransaction(kind=2, issue_valid=1, activity_mask=0b1111, issue_layer_output=0),
        GateTransaction(kind=2, issue_valid=1, activity_mask=0b0101, issue_layer_output=1),
        GateTransaction(kind=0, mode=Mode.CONFIG, opcode=Opcode.PRUNE_CLEAR),
    ]
    for mask in LEGAL_MASKS:
        transactions.append(GateTransaction(kind=1, mode=Mode.CONFIG, cfg_mask=mask))
        for activity in range(16):
            transactions.append(
                GateTransaction(
                    kind=2,
                    issue_valid=1,
                    activity_mask=activity,
                    issue_layer_output=(activity ^ mask) & 1,
                )
            )
        transactions.append(GateTransaction(kind=0, mode=Mode.CONFIG, opcode=Opcode.PRUNE_CLEAR))
    transactions.extend(
        (
            GateTransaction(kind=1, mode=Mode.CONFIG, cfg_mask=0b0001),
            GateTransaction(kind=1, mode=Mode.TRAIN, cfg_mask=0b0011),
            GateTransaction(
                kind=0,
                mode=Mode.TRAIN,
                opcode=Opcode.PRUNE_COMMIT,
                txn_id=0xFFFF,
                inject_busy_command=1,
            ),
        )
    )
    return transactions


def make_transactions(*, seed: int, transaction_count: int) -> list[GateTransaction]:
    if transaction_count < 1:
        raise ValueError("transaction_count must be positive")
    rng = random.Random(seed)
    directed = _directed_prefix()
    transactions = directed[:transaction_count]
    while len(transactions) < transaction_count:
        phase = len(transactions) % 17
        if phase in (0, 1, 2, 3, 4, 5, 6):
            kind = 0
            opcode = rng.randrange(8)
        elif phase in (7, 8):
            kind = 1
            opcode = Opcode.MASK_READ
        else:
            kind = 2
            opcode = Opcode.MASK_READ
        evidence = pack_levels(tuple(rng.randrange(4) for _ in range(4)))
        id_candidates = (0, 1, 2, 3, 0xFFFE, 0xFFFF, rng.randrange(0x10000))
        transactions.append(
            GateTransaction(
                kind=kind,
                mode=rng.randrange(4),
                opcode=opcode,
                txn_id=rng.choice(id_candidates),
                raw_evidence_flat=evidence,
                modulator_nonzero=rng.randrange(2),
                core_idle=rng.randrange(2),
                pending_snapshot=rng.randrange(2),
                pending_mod_commit=rng.randrange(2),
                issue_valid=rng.randrange(2),
                activity_mask=rng.randrange(16),
                issue_layer_output=rng.randrange(2),
                cfg_mask=rng.randrange(16),
                response_hold_cycles=rng.randrange(8),
                inject_busy_command=rng.randrange(2),
            )
        )
    return transactions


def expected_rows(
    *, model_name: str, transactions: list[GateTransaction]
) -> list[tuple[int, ...]]:
    model = LocalPruneRtlReference(model_name=model_name)
    return [model.apply(transaction) for transaction in transactions]


def _make_testbench(*, gain_module: str, atomic_monitor: bool = True) -> str:
    monitor = """
      if (dut.state == 1'b1 && structural_mask_state !== commit_old_mask)
        $fatal(1, "ATOMIC_MASK_VIOLATION old=%h current=%h", commit_old_mask, structural_mask_state);
""" if atomic_monitor else ""
    return f"""
module tb;
  logic clk = 1'b0; always #5 clk = ~clk;
  logic rst;
  logic [1:0] mode_state;
  logic cmd_valid, cmd_ready;
  logic [2:0] cmd_opcode;
  logic [15:0] cmd_id;
  logic [7:0] raw_evidence_flat, scaled_evidence_flat, evidence_levels_flat;
  logic modulator_nonzero, core_idle, pending_snapshot, pending_mod_commit;
  logic rsp_valid, rsp_ready;
  logic [2:0] rsp_status;
  logic [15:0] rsp_id;
  logic [3:0] rsp_mask;
  logic cfg_mask_valid, cfg_mask_ready, cfg_mask_done, cfg_mask_error;
  logic [3:0] cfg_mask_data;
  logic issue_valid, issue_layer_output;
  logic [3:0] activity_mask, issue_mask;
  logic busy, protocol_error, fsm_state;
  logic [1:0] scan_index_state;
  logic [15:0] utility_flat;
  logic [3:0] structural_mask_state;
  logic mask_valid_state, last_observation_valid_state, last_commit_valid_state;
  logic [15:0] last_observation_id_state, last_commit_id_state;
  logic [31:0] mask_commits_state, illegal_commands_state;
  logic [31:0] hidden_dense_reads_state, hidden_reads_issued_state;
  logic [31:0] hidden_synapse_ops_state, hidden_reads_saved_state;
  logic [31:0] output_dense_reads_state, output_reads_issued_state;
  logic [31:0] output_synapse_ops_state, output_reads_saved_state;
  logic [31:0] inactive_groups_state, groups_skipped_state;
  logic [3:0] commit_old_mask;

  assign evidence_levels_flat = scaled_evidence_flat;
  {gain_module} gain_adapter(.*);
  local_prune_gate_2of4 dut(.*);

  integer fd, parsed, kind, mode_i, opcode_i, txn_id_i, evidence_i;
  integer mod_i, idle_i, snap_i, mod_pending_i, issue_i, activity_i;
  integer layer_i, cfg_i, hold_i, inject_i, wait_cycles, response_status_i;
  integer legal_commit_i;
  reg [1023:0] command_file;

  task automatic print_row(input integer row_kind, input integer row_status,
                           input integer response_id_i, input integer response_mask_i,
                           input integer cfg_error_i);
    begin
      $display("ROW %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
        row_kind, row_status, response_id_i, response_mask_i, cfg_error_i,
        utility_flat, structural_mask_state, mask_valid_state,
        last_observation_valid_state, last_observation_id_state,
        last_commit_valid_state, last_commit_id_state, mask_commits_state,
        illegal_commands_state, hidden_dense_reads_state, hidden_reads_issued_state,
        hidden_synapse_ops_state, hidden_reads_saved_state, output_dense_reads_state,
        output_reads_issued_state, output_synapse_ops_state, output_reads_saved_state,
        inactive_groups_state, groups_skipped_state);
    end
  endtask

  always @(posedge clk) begin
    #1;
    if (!rst) begin
      if (mask_valid_state && !((structural_mask_state == 4'b0011)
          || (structural_mask_state == 4'b0101) || (structural_mask_state == 4'b0110)
          || (structural_mask_state == 4'b1001) || (structural_mask_state == 4'b1010)
          || (structural_mask_state == 4'b1100)))
        $fatal(1, "ILLEGAL_VISIBLE_MASK %h", structural_mask_state);
{monitor}
    end
  end

  initial begin
    if (!$value$plusargs("CMDFILE=%s", command_file)) $fatal(1, "missing CMDFILE");
    fd = $fopen(command_file, "r");
    if (!fd) $fatal(1, "cannot open command file");
    rst = 1'b1; mode_state = 0; cmd_valid = 0; cmd_opcode = 0; cmd_id = 0;
    raw_evidence_flat = 0; modulator_nonzero = 0; core_idle = 1;
    pending_snapshot = 0; pending_mod_commit = 0; rsp_ready = 0;
    cfg_mask_valid = 0; cfg_mask_data = 0; issue_valid = 0;
    activity_mask = 0; issue_layer_output = 0; commit_old_mask = 4'hf;
    repeat (2) @(posedge clk); #1; rst = 1'b0;

    while (!$feof(fd)) begin
      parsed = $fscanf(fd, "%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\\n",
        kind, mode_i, opcode_i, txn_id_i, evidence_i, mod_i, idle_i, snap_i,
        mod_pending_i, issue_i, activity_i, layer_i, cfg_i, hold_i, inject_i);
      if (parsed != 15) begin
        if (!$feof(fd)) $fatal(1, "bad command row parsed=%0d", parsed);
      end else begin
        mode_state = mode_i[1:0]; cmd_opcode = opcode_i[2:0]; cmd_id = txn_id_i[15:0];
        raw_evidence_flat = evidence_i[7:0]; modulator_nonzero = mod_i[0];
        core_idle = idle_i[0]; pending_snapshot = snap_i[0];
        pending_mod_commit = mod_pending_i[0]; issue_valid = issue_i[0];
        activity_mask = activity_i[3:0]; issue_layer_output = layer_i[0];
        cfg_mask_data = cfg_i[3:0]; rsp_ready = 1'b0;

        if (kind == 0) begin
          while (!cmd_ready) @(posedge clk);
          commit_old_mask = structural_mask_state;
          legal_commit_i = (opcode_i == 2) && (mode_i == 1) && idle_i
            && !snap_i && !mod_pending_i && !issue_i && !mask_valid_state
            && (!last_commit_valid_state || (txn_id_i > last_commit_id_state));
          cmd_valid = 1'b1;
          @(posedge clk); #1;
          cmd_valid = 1'b0; issue_valid = 1'b0;
          wait_cycles = 0;
          while (!rsp_valid) begin
            if (inject_i) begin
              cmd_valid = 1'b1;
              cmd_opcode = 3'd0;
              cmd_id = txn_id_i[15:0] ^ 16'h55aa;
              raw_evidence_flat = 8'hff;
              modulator_nonzero = 1'b1;
            end
            @(posedge clk); #1;
            wait_cycles = wait_cycles + 1;
            if (wait_cycles > 16) $fatal(1, "response timeout");
          end
          if (legal_commit_i && wait_cycles != 4)
            $fatal(1, "commit latency mismatch got=%0d expected=4", wait_cycles);
          if (!legal_commit_i && wait_cycles != 0)
            $fatal(1, "single-cycle command latency mismatch got=%0d", wait_cycles);
          cmd_valid = 1'b0;
          response_status_i = rsp_status;
          repeat (hold_i) begin
            if (inject_i) begin
              cmd_valid = 1'b1;
              cmd_opcode = 3'd7;
              cmd_id = 16'hffff;
            end
            @(posedge clk); #1;
            if (!rsp_valid || rsp_status != response_status_i)
              $fatal(1, "response changed under backpressure");
          end
          cmd_valid = 1'b0;
          print_row(kind, rsp_status, rsp_id, rsp_mask, 0);
          rsp_ready = 1'b1; @(posedge clk); #1; rsp_ready = 1'b0;
        end else if (kind == 1) begin
          while (!cfg_mask_ready) @(posedge clk);
          cfg_mask_valid = 1'b1;
          @(posedge clk); #1;
          cfg_mask_valid = 1'b0; issue_valid = 1'b0;
          if (!cfg_mask_done) $fatal(1, "config write missing done");
          print_row(kind, 0, 0, structural_mask_state, cfg_mask_error);
        end else begin
          @(posedge clk); #1;
          issue_valid = 1'b0;
          print_row(kind, 0, 0, structural_mask_state, 0);
        end
      end
    end
    $fclose(fd);
    $finish;
  end
endmodule
"""


def _parse_rows(output: str) -> list[tuple[int, ...]]:
    rows: list[tuple[int, ...]] = []
    for line in output.splitlines():
        match = ROW_RE.fullmatch(line.strip())
        if match:
            rows.append(tuple(int(value) for value in match.groups()))
    return rows


def _run_iverilog(
    *,
    model_name: str,
    transactions: list[GateTransaction],
    gate_source: Path | None = None,
    atomic_monitor: bool = True,
) -> list[tuple[int, ...]]:
    iverilog = find_tool("iverilog")
    vvp = find_tool("vvp")
    if iverilog is None or vvp is None:
        raise RuntimeError("需要 Icarus Verilog；已检查 PATH 和 C:/msys64")
    if model_name not in GAIN_MODULES:
        raise ValueError(f"unknown model: {model_name}")
    source = gate_source or ROOT / "local_prune_gate_2of4.sv"
    with tempfile.TemporaryDirectory(prefix="local_prune_gate_") as temp_dir:
        temp = Path(temp_dir)
        command_path = temp / "commands.txt"
        testbench_path = temp / "tb.sv"
        simulation_path = temp / "tb.vvp"
        command_path.write_text(
            "".join(transaction.as_line() + "\n" for transaction in transactions),
            encoding="ascii",
        )
        testbench_path.write_text(
            _make_testbench(
                gain_module=GAIN_MODULES[model_name],
                atomic_monitor=atomic_monitor,
            ),
            encoding="utf-8",
        )
        compile_result = subprocess.run(
            [
                str(iverilog),
                "-g2012",
                "-Wall",
                "-s",
                "tb",
                "-o",
                str(simulation_path),
                str(source),
                str(ROOT / "local_prune_evidence_gain.sv"),
                str(testbench_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if compile_result.returncode:
            raise RuntimeError(compile_result.stdout + compile_result.stderr)
        environment = os.environ.copy()
        environment["PATH"] = f"{vvp.parent}{os.pathsep}{environment.get('PATH', '')}"
        simulation_result = subprocess.run(
            [str(vvp), str(simulation_path), f"+CMDFILE={command_path}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        if simulation_result.returncode:
            raise RuntimeError(simulation_result.stdout + simulation_result.stderr)
        return _parse_rows(simulation_result.stdout)


def run_mixed_cosim(*, model_name: str, seed: int, transaction_count: int) -> None:
    transactions = make_transactions(seed=seed, transaction_count=transaction_count)
    expected = expected_rows(model_name=model_name, transactions=transactions)
    actual = _run_iverilog(model_name=model_name, transactions=transactions)
    if len(actual) != len(expected):
        raise AssertionError(f"row count differs actual={len(actual)} expected={len(expected)}")
    for index, (got, want) in enumerate(zip(actual, expected)):
        if got != want:
            raise AssertionError(
                f"model={model_name} seed={seed} transaction={index}\n"
                f"input={transactions[index]}\ngot={got}\nwant={want}"
            )
    LOGGER.info(
        "local prune cosim passed model=%s seed=%d transactions=%d",
        model_name,
        seed,
        transaction_count,
    )


def run_directed_contract() -> None:
    for model_name in GAIN_MODULES:
        run_mixed_cosim(
            model_name=model_name,
            seed=0,
            transaction_count=len(_directed_prefix()),
        )


def _mutated_source(temp: Path, *, replacement: tuple[str, str]) -> Path:
    original = (ROOT / "local_prune_gate_2of4.sv").read_text(encoding="utf-8")
    before, after = replacement
    if original.count(before) != 1:
        raise AssertionError("mutation anchor must occur exactly once")
    path = temp / "local_prune_gate_2of4_mutant.sv"
    path.write_text(original.replace(before, after), encoding="utf-8")
    return path


def run_negative_controls() -> None:
    tie_witness = [
        GateTransaction(kind=0, mode=Mode.CONFIG, opcode=Opcode.PRUNE_CLEAR),
        GateTransaction(kind=0, mode=Mode.TRAIN, opcode=Opcode.PRUNE_COMMIT, txn_id=1),
    ]
    atomic_witness = [
        GateTransaction(kind=0, mode=Mode.CONFIG, opcode=Opcode.PRUNE_CLEAR),
        GateTransaction(
            kind=0,
            mode=Mode.TRAIN,
            opcode=Opcode.OBSERVE,
            txn_id=1,
            raw_evidence_flat=pack_levels((3, 2, 1, 0)),
            modulator_nonzero=1,
        ),
        GateTransaction(kind=0, mode=Mode.TRAIN, opcode=Opcode.PRUNE_COMMIT, txn_id=2),
    ]
    with tempfile.TemporaryDirectory(prefix="local_prune_mutants_") as temp_dir:
        temp = Path(temp_dir)
        tie_source = _mutated_source(
            temp,
            replacement=(
                "utility[scan_index] > best1_score",
                "utility[scan_index] >= best1_score",
            ),
        )
        actual = _run_iverilog(
            model_name="eneuron",
            transactions=tie_witness,
            gate_source=tie_source,
        )
        expected = expected_rows(model_name="eneuron", transactions=tie_witness)
        if actual == expected:
            raise AssertionError("tie-break mutant did not produce a counterexample")

        atomic_source = _mutated_source(
            temp,
            replacement=(
                "best1_index <= next_best1_index;",
                "best1_index <= next_best1_index;\n"
                "                    structural_mask <= 4'b0001 << next_best1_index;",
            ),
        )
        try:
            _run_iverilog(
                model_name="eneuron",
                transactions=atomic_witness,
                gate_source=atomic_source,
            )
        except RuntimeError as error:
            if "ATOMIC_MASK_VIOLATION" not in str(error):
                raise
        else:
            raise AssertionError("non-atomic mutant did not produce a counterexample")
    LOGGER.info("local prune negative controls produced both expected counterexamples")


def run_full_regression() -> None:
    total = 0
    for model_name in GAIN_MODULES:
        for seed in range(20):
            run_mixed_cosim(model_name=model_name, seed=seed, transaction_count=1000)
            total += 1000
    run_negative_controls()
    print(f"LOCAL_PRUNE_GATE_COSIM_PASS models=3 seeds=20 transactions={total}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_full_regression()

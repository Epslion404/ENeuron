// Host Bridge controller bounded-formal harness with an abstract single-slot Tile.
module formal_host_bridge_controller (
    input logic clk,
    input logic break_tile_contract,
    input logic untrusted_tile_done,
    output logic abstract_tile_contract_ok,
    output logic cover_response_stall,
    output logic cover_arch_commit,
    output logic cover_protocol_error,
    output logic cover_fatal,
    output logic cover_weight_read,
    output logic cover_train_ep_end
);

    localparam logic [7:0] OP_EP_START     = 8'h01;
    localparam logic [7:0] OP_TICK_COMMIT  = 8'h04;
    localparam logic [7:0] OP_EP_END       = 8'h05;
    localparam logic [7:0] OP_MOD_COMMIT   = 8'h06;
    localparam logic [7:0] OP_WEIGHT_WRITE = 8'h07;
    localparam logic [7:0] OP_WEIGHT_READ  = 8'h08;
    localparam logic [7:0] OP_ABORT        = 8'h09;
    localparam logic [7:0] ST_OK            = 8'h00;
    localparam logic [7:0] ST_INTERNAL_FATAL = 8'h0f;

    localparam logic [3:0] S_IDLE                = 4'd0;
    localparam logic [3:0] S_FLUSH_WAIT          = 4'd5;
    localparam logic [3:0] S_SNAPSHOT_LAUNCH     = 4'd6;
    localparam logic [3:0] S_SNAPSHOT_WAIT       = 4'd7;
    localparam logic [3:0] S_WEIGHT_READ_SETUP   = 4'd8;
    localparam logic [3:0] S_WEIGHT_READ_CAPTURE = 4'd9;
    localparam logic [3:0] S_RESPONSE            = 4'd10;

    localparam logic [5:0] REQ_CLEAR    = 6'b000001;
    localparam logic [5:0] REQ_TICK     = 6'b000010;
    localparam logic [5:0] REQ_FLUSH    = 6'b000100;
    localparam logic [5:0] REQ_SNAPSHOT = 6'b001000;
    localparam logic [5:0] REQ_MOD      = 6'b010000;
    localparam logic [5:0] REQ_WEIGHT   = 6'b100000;

    (* anyseq *) logic rst;
    (* anyseq *) logic cmd_valid;
    (* anyseq *) logic [127:0] cmd_data;
    (* anyseq *) logic rsp_ready;

    logic cmd_ready;
    logic rsp_valid;
    logic [127:0] rsp_data;

    logic tile_state_clear;
    logic tile_tick_valid;
    logic tile_route_flush_valid;
    logic [3:0] tile_input_spikes;
    logic tile_learn_enable;
    logic tile_snapshot_we;
    logic [15:0] tile_snapshot_commit_id;
    logic [15:0] tile_snapshot_episode_id;
    logic tile_mod_valid;
    logic [15:0] tile_mod_commit_id;
    logic signed [1:0] tile_hidden0_modulator;
    logic signed [1:0] tile_hidden1_modulator;
    logic signed [1:0] tile_output0_modulator;
    logic signed [1:0] tile_output1_modulator;
    logic tile_weight_we;
    logic [1:0] tile_neuron_addr;
    logic [1:0] tile_weight_addr;
    logic signed [7:0] tile_weight_wdata;

    logic signed [7:0] tile_weight_rdata;
    logic tile_ready;
    logic tile_done;
    logic modeled_tile_done;
    logic tile_protocol_error;
    logic [1:0] tile_hidden_spikes;
    logic [1:0] tile_output_spikes;
    logic tile_snapshot_valid_state;
    logic [15:0] tile_pending_commit_id_state;
    logic [15:0] tile_pending_episode_id_state;
    logic tile_last_commit_valid_state;
    logic [15:0] tile_last_commit_id_state;
    logic [31:0] tile_weight_epoch_state;

    // These wires are connected to controller-private registers by the Yosys runner.
    logic [3:0] observed_state;
    logic [2:0] observed_active_action;
    logic [127:0] observed_active_command_reg;
    logic [1:0] observed_ep_end_flush_spikes;
    logic observed_episode_active;
    logic observed_episode_train;
    logic [15:0] observed_active_episode_id;
    logic [16:0] observed_next_tick_ext;
    logic observed_tick_open;
    logic [2:0] observed_expected_event_count;
    logic [2:0] observed_seen_event_count;
    logic [3:0] observed_seen_mask;
    logic observed_pending_arch_valid;
    logic observed_pending_episode_active;
    logic observed_pending_episode_train;
    logic [15:0] observed_pending_active_episode_id;
    logic [16:0] observed_pending_next_tick_ext;
    logic observed_pending_tick_open;
    logic [2:0] observed_pending_expected_event_count;
    logic [2:0] observed_pending_seen_event_count;
    logic [3:0] observed_pending_seen_mask;
    logic observed_fatal_error;
    logic [7:0] observed_fatal_opcode;
    logic [7:0] observed_fatal_phase;

    digital_snn_host_bridge_controller dut (.*);

    wire command_accept = cmd_valid && cmd_ready;
    wire response_accept = rsp_valid && rsp_ready;
    wire [7:0] response_opcode = rsp_data[127:120];
    wire [7:0] response_status = rsp_data[119:112];
    wire [31:0] response_arg0 = rsp_data[63:32];

    wire [5:0] tile_request_bits = {
        tile_weight_we,
        tile_mod_valid,
        tile_snapshot_we,
        tile_route_flush_valid,
        tile_tick_valid,
        tile_state_clear
    };
    wire tile_request = |tile_request_bits;

    wire [63:0] observed_arch = {
        observed_episode_active,
        observed_episode_train,
        observed_active_episode_id,
        observed_next_tick_ext,
        observed_tick_open,
        observed_expected_event_count,
        observed_seen_event_count,
        observed_seen_mask,
        18'b0
    };
    wire [63:0] observed_pending_arch = {
        observed_pending_episode_active,
        observed_pending_episode_train,
        observed_pending_active_episode_id,
        observed_pending_next_tick_ext,
        observed_pending_tick_open,
        observed_pending_expected_event_count,
        observed_pending_seen_event_count,
        observed_pending_seen_mask,
        18'b0
    };

    // Abstract Tile: accepts exactly one request while ready, then completes once
    // after an arbitrary finite-or-infinite delay selected by the solver.
    (* anyseq *) logic tile_finish_now;
    (* anyseq *) logic tile_finish_error;
    (* anyseq *) logic [1:0] tile_finish_hidden_spikes;
    (* anyseq *) logic [1:0] tile_finish_output_spikes;

    logic tile_busy = 1'b0;
    logic tile_busy_past = 1'b0;
    logic [5:0] accepted_request = '0;
    logic [15:0] accepted_commit_id = '0;
    logic [15:0] accepted_episode_id = '0;

    assign tile_ready = !tile_busy;
    assign tile_done = break_tile_contract ? untrusted_tile_done : modeled_tile_done;
    assign abstract_tile_contract_ok = !tile_done || tile_busy_past;
    assign tile_weight_rdata = $signed({2'b10, tile_neuron_addr, tile_weight_addr, 2'b01});

    always_ff @(posedge clk) begin
        if (rst) begin
            tile_busy <= 1'b0;
            tile_busy_past <= 1'b0;
            accepted_request <= '0;
            accepted_commit_id <= '0;
            accepted_episode_id <= '0;
            modeled_tile_done <= 1'b0;
            tile_protocol_error <= 1'b0;
            tile_hidden_spikes <= '0;
            tile_output_spikes <= '0;
            tile_snapshot_valid_state <= 1'b0;
            tile_pending_commit_id_state <= '0;
            tile_pending_episode_id_state <= '0;
            tile_last_commit_valid_state <= 1'b0;
            tile_last_commit_id_state <= '0;
            tile_weight_epoch_state <= '0;
        end else begin
            tile_busy_past <= tile_busy;
            modeled_tile_done <= 1'b0;
            tile_protocol_error <= 1'b0;
            tile_hidden_spikes <= '0;
            tile_output_spikes <= '0;

            if (!tile_busy && tile_request) begin
                tile_busy <= 1'b1;
                accepted_request <= tile_request_bits;
                accepted_commit_id <= tile_snapshot_we
                    ? tile_snapshot_commit_id : tile_mod_commit_id;
                accepted_episode_id <= tile_snapshot_episode_id;
            end else if (tile_busy && tile_finish_now) begin
                tile_busy <= 1'b0;
                modeled_tile_done <= 1'b1;
                tile_protocol_error <= tile_finish_error;
                tile_hidden_spikes <= tile_finish_hidden_spikes;
                tile_output_spikes <= tile_finish_output_spikes;
                if (!tile_finish_error) begin
                    if (accepted_request == REQ_SNAPSHOT) begin
                        tile_snapshot_valid_state <= 1'b1;
                        tile_pending_commit_id_state <= accepted_commit_id;
                        tile_pending_episode_id_state <= accepted_episode_id;
                        tile_last_commit_valid_state <= 1'b1;
                        tile_last_commit_id_state <= accepted_commit_id;
                    end else if (accepted_request == REQ_MOD) begin
                        tile_snapshot_valid_state <= 1'b0;
                        tile_weight_epoch_state <= tile_weight_epoch_state + 1'b1;
                    end
                end
            end
        end
    end

    logic past_valid = 1'b0;
    logic command_inflight = 1'b0;
    logic [5:0] launch_seen = '0;
    logic [1:0] launch_count = '0;
    logic flush_success_seen = 1'b0;
    logic [1:0] captured_flush_spikes = '0;

    // Sticky reachability outputs let the runner require non-vacuous traces.
    initial begin
        cover_response_stall = 1'b0;
        cover_arch_commit = 1'b0;
        cover_protocol_error = 1'b0;
        cover_fatal = 1'b0;
        cover_weight_read = 1'b0;
        cover_train_ep_end = 1'b0;
    end

    always_ff @(posedge clk) begin
        past_valid <= 1'b1;
        if (!past_valid) begin
            assume(rst);
            command_inflight <= 1'b0;
            launch_seen <= '0;
            launch_count <= '0;
            flush_success_seen <= 1'b0;
        end else begin
            assume(!rst);

            // Host valid/data must obey the ordinary ready/valid hold contract.
            if ($past(cmd_valid && !cmd_ready)) begin
                assume(cmd_valid);
                assume(cmd_data == $past(cmd_data));
            end

            assert(tile_request_bits == 0 || $onehot(tile_request_bits));
            assert(abstract_tile_contract_ok);
            if (tile_request) begin
                assert(tile_ready);
                assert(command_inflight);
                assert((launch_seen & tile_request_bits) == 0);
                case (observed_active_command_reg[127:120])
                    OP_EP_START, OP_ABORT: begin
                        assert(tile_request_bits == REQ_CLEAR);
                        assert(launch_count == 0);
                    end
                    OP_TICK_COMMIT: begin
                        assert(tile_request_bits == REQ_TICK);
                        assert(launch_count == 0);
                    end
                    OP_EP_END: begin
                        if (tile_request_bits == REQ_FLUSH) begin
                            assert(launch_count == 0);
                        end else begin
                            assert(tile_request_bits == REQ_SNAPSHOT);
                            assert(launch_count == 1);
                            assert((launch_seen & REQ_FLUSH) != 0);
                        end
                    end
                    OP_MOD_COMMIT: begin
                        assert(tile_request_bits == REQ_MOD);
                        assert(launch_count == 0);
                    end
                    OP_WEIGHT_WRITE: begin
                        assert(tile_request_bits == REQ_WEIGHT);
                        assert(launch_count == 0);
                    end
                    default: assert(1'b0);
                endcase
                launch_seen <= launch_seen | tile_request_bits;
                launch_count <= launch_count + 1'b1;
            end

            if (command_accept) begin
                assert(!command_inflight);
                command_inflight <= 1'b1;
                launch_seen <= '0;
                launch_count <= '0;
                flush_success_seen <= 1'b0;
            end
            if (response_accept) begin
                assert(command_inflight);
                command_inflight <= 1'b0;
            end

            // A stalled response is a stable single-slot object.
            if ($past(rsp_valid && !rsp_ready)) begin
                assert(rsp_valid);
                assert(rsp_data == $past(rsp_data));
                cover_response_stall <= 1'b1;
            end

            // Architectural state changes exactly at response acceptance.
            if ($past(response_accept && observed_pending_arch_valid)) begin
                assert(observed_arch == $past(observed_pending_arch));
                cover_arch_commit <= 1'b1;
            end else begin
                assert(observed_arch == $past(observed_arch));
            end

            // Normal protocol errors must be decided before any Tile request.
            if (rsp_valid && (response_status != ST_OK)
                    && (response_status != ST_INTERNAL_FATAL)) begin
                assert(launch_seen == 0);
                cover_protocol_error <= 1'b1;
            end

            // First fatal cause is sticky until hard reset.
            if ($past(observed_fatal_error)) begin
                assert(observed_fatal_error);
                assert(observed_fatal_opcode == $past(observed_fatal_opcode));
                assert(observed_fatal_phase == $past(observed_fatal_phase));
            end else if (observed_fatal_error) begin
                assert(rsp_valid);
                assert(response_status == ST_INTERNAL_FATAL);
                cover_fatal <= 1'b1;
            end else begin
                assert(observed_fatal_opcode == 0);
                assert(observed_fatal_phase == 0);
            end

            // WEIGHT_READ uses an address setup cycle and captures only when ready.
            if (observed_state == S_WEIGHT_READ_SETUP) begin
                assert(!tile_request);
                assert(!rsp_valid);
            end
            if ($past(observed_state == S_WEIGHT_READ_SETUP)) begin
                assert(observed_state == S_WEIGHT_READ_CAPTURE);
                assert(tile_neuron_addr == $past(tile_neuron_addr));
                assert(tile_weight_addr == $past(tile_weight_addr));
            end
            if (observed_state == S_WEIGHT_READ_CAPTURE) begin
                assert(!tile_request);
                assert(!rsp_valid);
            end
            if ($past((observed_state == S_WEIGHT_READ_CAPTURE) && !tile_ready)) begin
                assert(observed_state == S_WEIGHT_READ_CAPTURE);
            end
            if ($past((observed_state == S_WEIGHT_READ_CAPTURE) && tile_ready)) begin
                assert(observed_state == S_RESPONSE);
                assert(rsp_valid);
                assert(response_opcode == OP_WEIGHT_READ);
                assert(response_status == ST_OK);
                assert(response_arg0 == {{24{$past(tile_weight_rdata[7])}},
                    $past(tile_weight_rdata)});
                cover_weight_read <= 1'b1;
            end

            // EP_END must finish flush before TRAIN snapshot and retain the spike.
            if ((observed_state == S_FLUSH_WAIT) && tile_done
                    && !tile_protocol_error) begin
                flush_success_seen <= 1'b1;
                captured_flush_spikes <= tile_output_spikes;
            end
            if ($past((observed_state == S_FLUSH_WAIT) && tile_done
                    && !tile_protocol_error)) begin
                assert(observed_ep_end_flush_spikes == $past(tile_output_spikes));
                if ($past(observed_episode_train))
                    assert(observed_state == S_SNAPSHOT_LAUNCH);
                else
                    assert(observed_state == S_RESPONSE);
            end
            if (tile_snapshot_we) begin
                assert(flush_success_seen);
                assert(observed_active_command_reg[127:120] == OP_EP_END);
            end
            if ((observed_state == S_SNAPSHOT_LAUNCH)
                    || (observed_state == S_SNAPSHOT_WAIT)) begin
                assert(flush_success_seen);
                assert(observed_ep_end_flush_spikes == captured_flush_spikes);
            end
            if (rsp_valid && (response_opcode == OP_EP_END)
                    && (response_status == ST_OK)) begin
                assert(flush_success_seen);
                assert(response_arg0[3:2] == captured_flush_spikes);
                assert(response_arg0[1:0] == 0);
                if (observed_episode_train) begin
                    assert((launch_seen & REQ_SNAPSHOT) != 0);
                    cover_train_ep_end <= 1'b1;
                end
            end
        end
    end

endmodule

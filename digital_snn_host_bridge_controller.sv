// Host Bridge V1 tile-clock controller: validates one 128-bit command at a time.
module digital_snn_host_bridge_controller (
    input  logic         clk,
    input  logic         rst,

    input  logic         cmd_valid,
    output logic         cmd_ready,
    input  logic [127:0] cmd_data,

    output logic         rsp_valid,
    input  logic         rsp_ready,
    output logic [127:0] rsp_data,

    output logic         tile_state_clear,
    output logic         tile_tick_valid,
    output logic         tile_route_flush_valid,
    output logic [3:0]   tile_input_spikes,
    output logic         tile_learn_enable,
    output logic         tile_snapshot_we,
    output logic [15:0]  tile_snapshot_commit_id,
    output logic [15:0]  tile_snapshot_episode_id,
    output logic         tile_mod_valid,
    output logic [15:0]  tile_mod_commit_id,
    output logic signed [1:0] tile_hidden0_modulator,
    output logic signed [1:0] tile_hidden1_modulator,
    output logic signed [1:0] tile_output0_modulator,
    output logic signed [1:0] tile_output1_modulator,
    output logic         tile_weight_we,
    output logic [1:0]   tile_neuron_addr,
    output logic [1:0]   tile_weight_addr,
    output logic signed [7:0] tile_weight_wdata,

    input  logic signed [7:0] tile_weight_rdata,
    input  logic         tile_ready,
    input  logic         tile_done,
    input  logic         tile_protocol_error,
    input  logic [1:0]   tile_hidden_spikes,
    input  logic [1:0]   tile_output_spikes,
    input  logic         tile_snapshot_valid_state,
    input  logic [15:0]  tile_pending_commit_id_state,
    input  logic [15:0]  tile_pending_episode_id_state,
    input  logic         tile_last_commit_valid_state,
    input  logic [15:0]  tile_last_commit_id_state,
    input  logic [31:0]  tile_weight_epoch_state
);

    localparam logic [7:0] OP_EP_START     = 8'h01;
    localparam logic [7:0] OP_TICK_BEGIN   = 8'h02;
    localparam logic [7:0] OP_INPUT_EVENT  = 8'h03;
    localparam logic [7:0] OP_TICK_COMMIT  = 8'h04;
    localparam logic [7:0] OP_EP_END       = 8'h05;
    localparam logic [7:0] OP_MOD_COMMIT   = 8'h06;
    localparam logic [7:0] OP_WEIGHT_WRITE = 8'h07;
    localparam logic [7:0] OP_WEIGHT_READ  = 8'h08;
    localparam logic [7:0] OP_ABORT        = 8'h09;
    localparam logic [7:0] OP_STATUS_READ  = 8'h0a;

    localparam logic [7:0] ST_OK             = 8'h00;
    localparam logic [7:0] ST_BAD_OPCODE     = 8'h01;
    localparam logic [7:0] ST_BAD_STATE      = 8'h02;
    localparam logic [7:0] ST_EPISODE_ID     = 8'h03;
    localparam logic [7:0] ST_TICK_ID        = 8'h04;
    localparam logic [7:0] ST_EVENT_COUNT    = 8'h05;
    localparam logic [7:0] ST_SYNAPSE_RANGE  = 8'h06;
    localparam logic [7:0] ST_DUP_EVENT      = 8'h07;
    localparam logic [7:0] ST_SNAPSHOT_BUSY  = 8'h09;
    localparam logic [7:0] ST_COMMIT_ID       = 8'h0a;
    localparam logic [7:0] ST_ADDRESS         = 8'h0b;
    localparam logic [7:0] ST_BAD_FIELD       = 8'h0c;
    localparam logic [7:0] ST_COUNTER_WRAP    = 8'h0e;
    localparam logic [7:0] ST_INTERNAL_FATAL  = 8'h0f;

    localparam logic [7:0] PH_NONE                 = 8'h00;
    localparam logic [7:0] PH_EP_START_CLEAR_WAIT  = 8'h01;
    localparam logic [7:0] PH_TICK_WAIT            = 8'h02;
    localparam logic [7:0] PH_EP_END_FLUSH_WAIT    = 8'h03;
    localparam logic [7:0] PH_EP_END_SNAPSHOT_WAIT = 8'h04;
    localparam logic [7:0] PH_MOD_WAIT             = 8'h05;
    localparam logic [7:0] PH_WEIGHT_WAIT          = 8'h06;
    localparam logic [7:0] PH_ABORT_CLEAR_WAIT     = 8'h07;
    localparam logic [7:0] PH_CONTROLLER_INTERNAL  = 8'h08;

    typedef enum logic [3:0] {
        S_IDLE,
        S_DECODE,
        S_TILE_LAUNCH,
        S_TILE_WAIT,
        S_FLUSH_LAUNCH,
        S_FLUSH_WAIT,
        S_SNAPSHOT_LAUNCH,
        S_SNAPSHOT_WAIT,
        S_WEIGHT_READ_SETUP,
        S_WEIGHT_READ_CAPTURE,
        S_RESPONSE
    } state_t;

    typedef enum logic [2:0] {
        A_NONE,
        A_EP_START_CLEAR,
        A_TICK,
        A_MOD,
        A_WEIGHT,
        A_ABORT_CLEAR
    } action_t;

    state_t state;
    action_t active_action;
    logic [127:0] active_command_reg;
    logic [127:0] response_reg;
    logic [1:0] ep_end_flush_spikes;

    logic episode_active;
    logic episode_train;
    logic [15:0] active_episode_id;
    logic [16:0] next_tick_ext;
    logic tick_open;
    logic [2:0] expected_event_count;
    logic [2:0] seen_event_count;
    logic [3:0] seen_mask;

    logic pending_arch_valid;
    logic pending_episode_active;
    logic pending_episode_train;
    logic [15:0] pending_active_episode_id;
    logic [16:0] pending_next_tick_ext;
    logic pending_tick_open;
    logic [2:0] pending_expected_event_count;
    logic [2:0] pending_seen_event_count;
    logic [3:0] pending_seen_mask;

    logic fatal_error;
    logic [7:0] fatal_opcode;
    logic [7:0] fatal_phase;

    wire [7:0] cmd_opcode = active_command_reg[127:120];
    wire [7:0] cmd_flags = active_command_reg[119:112];
    wire [15:0] cmd_txn_id = active_command_reg[111:96];
    wire [15:0] cmd_episode_id = active_command_reg[95:80];
    wire [15:0] cmd_tick_id = active_command_reg[79:64];
    wire [31:0] cmd_arg0 = active_command_reg[63:32];
    wire [31:0] cmd_arg1 = active_command_reg[31:0];

    wire [2:0] event_count_field = cmd_arg0[2:0];
    wire [2:0] synapse_field = cmd_arg0[2:0];
    wire [1:0] neuron_field = cmd_arg0[1:0];
    wire [1:0] weight_field = cmd_arg0[3:2];
    wire weight_address_valid = (neuron_field < 2) || (weight_field < 2);
    function automatic logic opcode_valid(input logic [7:0] opcode);
        begin
            opcode_valid = (opcode >= OP_EP_START) && (opcode <= OP_STATUS_READ);
        end
    endfunction

    function automatic logic static_bad_field(input logic [127:0] command_value);
        logic [7:0] opcode;
        logic [7:0] flags;
        logic [15:0] episode_id;
        logic [15:0] tick_id;
        logic [31:0] arg0;
        logic [31:0] arg1;
        begin
            opcode = command_value[127:120];
            flags = command_value[119:112];
            episode_id = command_value[95:80];
            tick_id = command_value[79:64];
            arg0 = command_value[63:32];
            arg1 = command_value[31:0];
            static_bad_field = 1'b0;
            case (opcode)
                OP_EP_START:
                    static_bad_field = (flags[7:1] != 0) || (tick_id != 0)
                        || (arg0 != 0) || (arg1 != 0);
                OP_TICK_BEGIN:
                    static_bad_field = (flags != 0) || (arg0[31:3] != 0) || (arg1 != 0);
                OP_INPUT_EVENT:
                    static_bad_field = (flags != 0) || (arg0[31:3] != 0) || (arg1 != 0);
                OP_TICK_COMMIT:
                    static_bad_field = (flags != 0) || (arg0 != 0) || (arg1 != 0);
                OP_EP_END:
                    static_bad_field = (flags != 0) || (tick_id != 0)
                        || (arg0[31:16] != 0) || (arg1 != 0);
                OP_MOD_COMMIT:
                    static_bad_field = (flags != 0) || (tick_id != 0)
                        || (arg0[31:16] != 0) || (arg1[31:8] != 0)
                        || (arg1[1:0] == 2'b10)
                        || (arg1[3:2] == 2'b10)
                        || (arg1[5:4] == 2'b10)
                        || (arg1[7:6] == 2'b10);
                OP_WEIGHT_WRITE:
                    static_bad_field = (flags != 0) || (episode_id != 0) || (tick_id != 0)
                        || (arg0[31:12] != 0) || (arg1 != 0);
                OP_WEIGHT_READ:
                    static_bad_field = (flags != 0) || (episode_id != 0) || (tick_id != 0)
                        || (arg0[31:4] != 0) || (arg1 != 0);
                OP_ABORT:
                    static_bad_field = (flags != 0) || (tick_id != 0)
                        || (arg0 != 0) || (arg1 != 0);
                OP_STATUS_READ:
                    static_bad_field = (flags != 0) || (episode_id != 0) || (tick_id != 0)
                        || (arg0[31:1] != 0) || (arg1 != 0);
                default: static_bad_field = 1'b0;
            endcase
        end
    endfunction

    function automatic logic [127:0] make_response(
        input logic [7:0] status,
        input logic [15:0] response_episode,
        input logic [15:0] response_tick,
        input logic [31:0] response_arg0,
        input logic [31:0] response_arg1
    );
        begin
            make_response = {
                cmd_opcode,
                status,
                cmd_txn_id,
                response_episode,
                response_tick,
                response_arg0,
                response_arg1
            };
        end
    endfunction

    task automatic prepare_arch_current;
        begin
            pending_episode_active <= episode_active;
            pending_episode_train <= episode_train;
            pending_active_episode_id <= active_episode_id;
            pending_next_tick_ext <= next_tick_ext;
            pending_tick_open <= tick_open;
            pending_expected_event_count <= expected_event_count;
            pending_seen_event_count <= seen_event_count;
            pending_seen_mask <= seen_mask;
        end
    endtask

    task automatic enter_fatal(input logic [7:0] phase_value);
        begin
            if (!fatal_error) begin
                fatal_error <= 1'b1;
                fatal_opcode <= cmd_opcode;
                fatal_phase <= phase_value;
            end
            pending_arch_valid <= 1'b0;
            response_reg <= make_response(
                ST_INTERNAL_FATAL, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
            );
            state <= S_RESPONSE;
        end
    endtask

    assign cmd_ready = (state == S_IDLE) && rsp_ready;
    assign rsp_valid = state == S_RESPONSE;
    assign rsp_data = response_reg;

    // Tile payload is driven only from the latched command, never live Host data.
    assign tile_input_spikes = seen_mask;
    assign tile_snapshot_commit_id = cmd_arg0[15:0];
    assign tile_snapshot_episode_id = cmd_episode_id;
    assign tile_mod_commit_id = cmd_arg0[15:0];
    assign tile_hidden0_modulator = cmd_arg1[1:0];
    assign tile_hidden1_modulator = cmd_arg1[3:2];
    assign tile_output0_modulator = cmd_arg1[5:4];
    assign tile_output1_modulator = cmd_arg1[7:6];
    assign tile_neuron_addr = neuron_field;
    assign tile_weight_addr = weight_field;
    assign tile_weight_wdata = cmd_arg0[11:4];

    always_comb begin
        tile_state_clear = 1'b0;
        tile_tick_valid = 1'b0;
        tile_route_flush_valid = 1'b0;
        tile_learn_enable = 1'b0;
        tile_snapshot_we = 1'b0;
        tile_mod_valid = 1'b0;
        tile_weight_we = 1'b0;

        if (state == S_TILE_LAUNCH && tile_ready) begin
            case (active_action)
                A_EP_START_CLEAR, A_ABORT_CLEAR: tile_state_clear = 1'b1;
                A_TICK: begin
                    tile_tick_valid = 1'b1;
                    tile_learn_enable = episode_train;
                end
                A_MOD: begin
                    tile_mod_valid = 1'b1;
                    tile_learn_enable = 1'b1;
                end
                A_WEIGHT: begin
                    tile_weight_we = 1'b1;
                    tile_learn_enable = 1'b1;
                end
                default: begin end
            endcase
        end

        if (state == S_FLUSH_LAUNCH && tile_ready) begin
            tile_route_flush_valid = 1'b1;
            tile_learn_enable = episode_train;
        end

        if (state == S_SNAPSHOT_LAUNCH && tile_ready) begin
            tile_snapshot_we = 1'b1;
            tile_learn_enable = 1'b1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            active_action <= A_NONE;
            active_command_reg <= '0;
            response_reg <= '0;
            ep_end_flush_spikes <= '0;
            episode_active <= 1'b0;
            episode_train <= 1'b0;
            active_episode_id <= '0;
            next_tick_ext <= '0;
            tick_open <= 1'b0;
            expected_event_count <= '0;
            seen_event_count <= '0;
            seen_mask <= '0;
            pending_arch_valid <= 1'b0;
            pending_episode_active <= 1'b0;
            pending_episode_train <= 1'b0;
            pending_active_episode_id <= '0;
            pending_next_tick_ext <= '0;
            pending_tick_open <= 1'b0;
            pending_expected_event_count <= '0;
            pending_seen_event_count <= '0;
            pending_seen_mask <= '0;
            fatal_error <= 1'b0;
            fatal_opcode <= '0;
            fatal_phase <= PH_NONE;
        end else begin
            case (state)
                S_IDLE: begin
                    active_action <= A_NONE;
                    pending_arch_valid <= 1'b0;
                    if (cmd_valid && cmd_ready) begin
                        active_command_reg <= cmd_data;
                        state <= S_DECODE;
                    end
                end

                S_DECODE: begin
                    if (fatal_error && (cmd_opcode != OP_STATUS_READ)) begin
                        response_reg <= make_response(
                            ST_INTERNAL_FATAL, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                        );
                        state <= S_RESPONSE;
                    end else if (!opcode_valid(cmd_opcode)) begin
                        response_reg <= make_response(
                            ST_BAD_OPCODE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                        );
                        state <= S_RESPONSE;
                    end else if (static_bad_field(active_command_reg)) begin
                        response_reg <= make_response(
                            ST_BAD_FIELD, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                        );
                        state <= S_RESPONSE;
                    end else begin
                        case (cmd_opcode)
                            OP_EP_START: begin
                                if (episode_active) begin
                                    response_reg <= make_response(
                                        ST_BAD_STATE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_flags[0] && tile_snapshot_valid_state) begin
                                    response_reg <= make_response(
                                        ST_SNAPSHOT_BUSY, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_flags[0] && tile_last_commit_valid_state
                                        && (tile_last_commit_id_state == 16'hffff)) begin
                                    response_reg <= make_response(
                                        ST_COUNTER_WRAP, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else begin
                                    active_action <= A_EP_START_CLEAR;
                                    state <= S_TILE_LAUNCH;
                                end
                            end

                            OP_TICK_BEGIN: begin
                                if (!episode_active || tick_open) begin
                                    response_reg <= make_response(
                                        ST_BAD_STATE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_episode_id != active_episode_id) begin
                                    response_reg <= make_response(
                                        ST_EPISODE_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (next_tick_ext[16]) begin
                                    response_reg <= make_response(
                                        ST_COUNTER_WRAP, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_tick_id != next_tick_ext[15:0]) begin
                                    response_reg <= make_response(
                                        ST_TICK_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (event_count_field > 4) begin
                                    response_reg <= make_response(
                                        ST_EVENT_COUNT, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else begin
                                    prepare_arch_current();
                                    pending_tick_open <= 1'b1;
                                    pending_expected_event_count <= event_count_field;
                                    pending_seen_event_count <= 3'b0;
                                    pending_seen_mask <= 4'b0;
                                    pending_arch_valid <= 1'b1;
                                    response_reg <= make_response(
                                        ST_OK, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end
                            end

                            OP_INPUT_EVENT: begin
                                if (!episode_active || !tick_open) begin
                                    response_reg <= make_response(
                                        ST_BAD_STATE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_episode_id != active_episode_id) begin
                                    response_reg <= make_response(
                                        ST_EPISODE_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_tick_id != next_tick_ext[15:0]) begin
                                    response_reg <= make_response(
                                        ST_TICK_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (synapse_field >= 4) begin
                                    response_reg <= make_response(
                                        ST_SYNAPSE_RANGE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (seen_mask[synapse_field]) begin
                                    response_reg <= make_response(
                                        ST_DUP_EVENT, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (seen_event_count >= expected_event_count) begin
                                    response_reg <= make_response(
                                        ST_EVENT_COUNT, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else begin
                                    prepare_arch_current();
                                    pending_seen_event_count <= seen_event_count + 1'b1;
                                    pending_seen_mask <= seen_mask | (4'b0001 << synapse_field);
                                    pending_arch_valid <= 1'b1;
                                    response_reg <= make_response(
                                        ST_OK, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end
                            end

                            OP_TICK_COMMIT: begin
                                if (!episode_active || !tick_open) begin
                                    response_reg <= make_response(
                                        ST_BAD_STATE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_episode_id != active_episode_id) begin
                                    response_reg <= make_response(
                                        ST_EPISODE_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_tick_id != next_tick_ext[15:0]) begin
                                    response_reg <= make_response(
                                        ST_TICK_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (seen_event_count != expected_event_count) begin
                                    response_reg <= make_response(
                                        ST_EVENT_COUNT, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else begin
                                    active_action <= A_TICK;
                                    state <= S_TILE_LAUNCH;
                                end
                            end

                            OP_EP_END: begin
                                if (!episode_active || tick_open) begin
                                    response_reg <= make_response(
                                        ST_BAD_STATE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_episode_id != active_episode_id) begin
                                    response_reg <= make_response(
                                        ST_EPISODE_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (!episode_train && (cmd_arg0[15:0] != 0)) begin
                                    response_reg <= make_response(
                                        ST_BAD_FIELD, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (episode_train && tile_snapshot_valid_state) begin
                                    response_reg <= make_response(
                                        ST_SNAPSHOT_BUSY, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (episode_train && tile_last_commit_valid_state
                                        && (tile_last_commit_id_state == 16'hffff)) begin
                                    response_reg <= make_response(
                                        ST_COUNTER_WRAP, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (episode_train && tile_last_commit_valid_state
                                        && (cmd_arg0[15:0] <= tile_last_commit_id_state)) begin
                                    response_reg <= make_response(
                                        ST_COMMIT_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else begin
                                    state <= S_FLUSH_LAUNCH;
                                end
                            end

                            OP_MOD_COMMIT: begin
                                if (episode_active) begin
                                    response_reg <= make_response(
                                        ST_BAD_STATE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (!tile_snapshot_valid_state) begin
                                    response_reg <= make_response(
                                        ST_COMMIT_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_episode_id != tile_pending_episode_id_state) begin
                                    response_reg <= make_response(
                                        ST_EPISODE_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_arg0[15:0] != tile_pending_commit_id_state) begin
                                    response_reg <= make_response(
                                        ST_COMMIT_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else begin
                                    active_action <= A_MOD;
                                    state <= S_TILE_LAUNCH;
                                end
                            end

                            OP_WEIGHT_READ: begin
                                if (episode_active) begin
                                    response_reg <= make_response(
                                        ST_BAD_STATE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (!weight_address_valid) begin
                                    response_reg <= make_response(
                                        ST_ADDRESS, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else begin
                                    state <= S_WEIGHT_READ_SETUP;
                                end
                            end

                            OP_WEIGHT_WRITE: begin
                                if (episode_active) begin
                                    response_reg <= make_response(
                                        ST_BAD_STATE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (tile_snapshot_valid_state) begin
                                    response_reg <= make_response(
                                        ST_SNAPSHOT_BUSY, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (!weight_address_valid) begin
                                    response_reg <= make_response(
                                        ST_ADDRESS, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else begin
                                    active_action <= A_WEIGHT;
                                    state <= S_TILE_LAUNCH;
                                end
                            end

                            OP_ABORT: begin
                                if (!episode_active) begin
                                    response_reg <= make_response(
                                        ST_BAD_STATE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else if (cmd_episode_id != active_episode_id) begin
                                    response_reg <= make_response(
                                        ST_EPISODE_ID, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                    state <= S_RESPONSE;
                                end else begin
                                    active_action <= A_ABORT_CLEAR;
                                    state <= S_TILE_LAUNCH;
                                end
                            end

                            OP_STATUS_READ: begin
                                if (!cmd_arg0[0]) begin
                                    response_reg <= make_response(
                                        ST_OK,
                                        episode_active ? active_episode_id : 16'b0,
                                        next_tick_ext[15:0],
                                        {
                                            14'b0, seen_mask, seen_event_count,
                                            expected_event_count, 3'b0,
                                            fatal_error, next_tick_ext[16], tick_open,
                                            episode_train, episode_active
                                        },
                                        {
                                            16'b0,
                                            fatal_error ? fatal_phase : 8'b0,
                                            fatal_error ? fatal_opcode : 8'b0
                                        }
                                    );
                                end else begin
                                    response_reg <= make_response(
                                        ST_OK,
                                        tile_snapshot_valid_state
                                            ? tile_pending_episode_id_state : 16'b0,
                                        tile_snapshot_valid_state
                                            ? tile_pending_commit_id_state : 16'b0,
                                        {
                                            14'b0,
                                            tile_last_commit_valid_state,
                                            tile_snapshot_valid_state,
                                            tile_last_commit_valid_state
                                                ? tile_last_commit_id_state : 16'b0
                                        },
                                        tile_weight_epoch_state
                                    );
                                end
                                state <= S_RESPONSE;
                            end

                            default: begin
                                response_reg <= make_response(
                                    ST_BAD_OPCODE, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                );
                                state <= S_RESPONSE;
                            end
                        endcase
                    end
                end

                S_TILE_LAUNCH: begin
                    if (tile_ready)
                        state <= S_TILE_WAIT;
                end

                S_TILE_WAIT: begin
                    if (tile_done) begin
                        if (tile_protocol_error) begin
                            case (active_action)
                                A_EP_START_CLEAR: enter_fatal(PH_EP_START_CLEAR_WAIT);
                                A_TICK: enter_fatal(PH_TICK_WAIT);
                                A_MOD: enter_fatal(PH_MOD_WAIT);
                                A_WEIGHT: enter_fatal(PH_WEIGHT_WAIT);
                                A_ABORT_CLEAR: enter_fatal(PH_ABORT_CLEAR_WAIT);
                                default: enter_fatal(PH_CONTROLLER_INTERNAL);
                            endcase
                        end else begin
                            case (active_action)
                                A_EP_START_CLEAR: begin
                                    prepare_arch_current();
                                    pending_episode_active <= 1'b1;
                                    pending_episode_train <= cmd_flags[0];
                                    pending_active_episode_id <= cmd_episode_id;
                                    pending_next_tick_ext <= 17'b0;
                                    pending_tick_open <= 1'b0;
                                    pending_expected_event_count <= 3'b0;
                                    pending_seen_event_count <= 3'b0;
                                    pending_seen_mask <= 4'b0;
                                    pending_arch_valid <= 1'b1;
                                    response_reg <= make_response(
                                        ST_OK, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                end
                                A_TICK: begin
                                    prepare_arch_current();
                                    pending_next_tick_ext <= next_tick_ext + 1'b1;
                                    pending_tick_open <= 1'b0;
                                    pending_expected_event_count <= 3'b0;
                                    pending_seen_event_count <= 3'b0;
                                    pending_seen_mask <= 4'b0;
                                    pending_arch_valid <= 1'b1;
                                    response_reg <= make_response(
                                        ST_OK, cmd_episode_id, cmd_tick_id,
                                        {28'b0, tile_output_spikes, tile_hidden_spikes}, 32'b0
                                    );
                                end
                                A_MOD: begin
                                    response_reg <= make_response(
                                        ST_OK, cmd_episode_id, cmd_tick_id,
                                        {16'b0, cmd_arg0[15:0]}, tile_weight_epoch_state
                                    );
                                end
                                A_WEIGHT: begin
                                    response_reg <= make_response(
                                        ST_OK, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                end
                                A_ABORT_CLEAR: begin
                                    prepare_arch_current();
                                    pending_episode_active <= 1'b0;
                                    pending_episode_train <= 1'b0;
                                    pending_active_episode_id <= 16'b0;
                                    pending_next_tick_ext <= 17'b0;
                                    pending_tick_open <= 1'b0;
                                    pending_expected_event_count <= 3'b0;
                                    pending_seen_event_count <= 3'b0;
                                    pending_seen_mask <= 4'b0;
                                    pending_arch_valid <= 1'b1;
                                    response_reg <= make_response(
                                        ST_OK, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                                    );
                                end
                                default: begin
                                    enter_fatal(PH_CONTROLLER_INTERNAL);
                                end
                            endcase
                            if (active_action != A_NONE)
                                state <= S_RESPONSE;
                        end
                    end
                end

                S_FLUSH_LAUNCH: begin
                    if (tile_ready)
                        state <= S_FLUSH_WAIT;
                end

                S_FLUSH_WAIT: begin
                    if (tile_done) begin
                        if (tile_protocol_error) begin
                            enter_fatal(PH_EP_END_FLUSH_WAIT);
                        end else begin
                            ep_end_flush_spikes <= tile_output_spikes;
                            if (episode_train) begin
                                state <= S_SNAPSHOT_LAUNCH;
                            end else begin
                                prepare_arch_current();
                                pending_episode_active <= 1'b0;
                                pending_episode_train <= 1'b0;
                                pending_active_episode_id <= 16'b0;
                                pending_next_tick_ext <= 17'b0;
                                pending_tick_open <= 1'b0;
                                pending_expected_event_count <= 3'b0;
                                pending_seen_event_count <= 3'b0;
                                pending_seen_mask <= 4'b0;
                                pending_arch_valid <= 1'b1;
                                response_reg <= make_response(
                                    ST_OK, cmd_episode_id, cmd_tick_id,
                                    {28'b0, tile_output_spikes, 2'b0},
                                    tile_weight_epoch_state
                                );
                                state <= S_RESPONSE;
                            end
                        end
                    end
                end

                S_SNAPSHOT_LAUNCH: begin
                    if (tile_ready)
                        state <= S_SNAPSHOT_WAIT;
                end

                S_SNAPSHOT_WAIT: begin
                    if (tile_done) begin
                        if (tile_protocol_error) begin
                            enter_fatal(PH_EP_END_SNAPSHOT_WAIT);
                        end else begin
                            prepare_arch_current();
                            pending_episode_active <= 1'b0;
                            pending_episode_train <= 1'b0;
                            pending_active_episode_id <= 16'b0;
                            pending_next_tick_ext <= 17'b0;
                            pending_tick_open <= 1'b0;
                            pending_expected_event_count <= 3'b0;
                            pending_seen_event_count <= 3'b0;
                            pending_seen_mask <= 4'b0;
                            pending_arch_valid <= 1'b1;
                            response_reg <= make_response(
                                ST_OK, cmd_episode_id, cmd_tick_id,
                                {28'b0, ep_end_flush_spikes, 2'b0},
                                tile_weight_epoch_state
                            );
                            state <= S_RESPONSE;
                        end
                    end
                end

                S_WEIGHT_READ_SETUP: begin
                    state <= S_WEIGHT_READ_CAPTURE;
                end

                S_WEIGHT_READ_CAPTURE: begin
                    if (tile_ready) begin
                        response_reg <= make_response(
                            ST_OK, cmd_episode_id, cmd_tick_id,
                            {{24{tile_weight_rdata[7]}}, tile_weight_rdata}, 32'b0
                        );
                        state <= S_RESPONSE;
                    end
                end

                S_RESPONSE: begin
                    if (rsp_ready) begin
                        if (pending_arch_valid) begin
                            episode_active <= pending_episode_active;
                            episode_train <= pending_episode_train;
                            active_episode_id <= pending_active_episode_id;
                            next_tick_ext <= pending_next_tick_ext;
                            tick_open <= pending_tick_open;
                            expected_event_count <= pending_expected_event_count;
                            seen_event_count <= pending_seen_event_count;
                            seen_mask <= pending_seen_mask;
                        end
                        pending_arch_valid <= 1'b0;
                        ep_end_flush_spikes <= 2'b0;
                        state <= S_IDLE;
                    end
                end

                default: begin
                    if (!fatal_error) begin
                        fatal_error <= 1'b1;
                        fatal_opcode <= cmd_opcode;
                        fatal_phase <= PH_CONTROLLER_INTERNAL;
                    end
                    pending_arch_valid <= 1'b0;
                    response_reg <= make_response(
                        ST_INTERNAL_FATAL, cmd_episode_id, cmd_tick_id, 32'b0, 32'b0
                    );
                    state <= S_RESPONSE;
                end
            endcase
        end
    end

endmodule

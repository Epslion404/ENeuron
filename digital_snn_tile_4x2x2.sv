// 4->2->2 数字 SNN tile：四个多周期神经元并行执行，片外 Host 提供训练调制。
module digital_snn_tile_4x2x2 #(
    parameter int COMMIT_BITS = 16,
    parameter int EPISODE_BITS = 16
) (
    input  logic                         clk,
    input  logic                         rst,
    input  logic                         state_clear,
    input  logic                         tick_valid,
    input  logic                         route_flush_valid,
    input  logic [3:0]                   input_spikes,
    input  logic                         learn_enable,
    input  logic                         snapshot_we,
    input  logic [COMMIT_BITS-1:0]       snapshot_commit_id,
    input  logic [EPISODE_BITS-1:0]      snapshot_episode_id,
    input  logic                         mod_valid,
    input  logic [COMMIT_BITS-1:0]       mod_commit_id,
    input  logic signed [1:0]            hidden0_modulator,
    input  logic signed [1:0]            hidden1_modulator,
    input  logic signed [1:0]            output0_modulator,
    input  logic signed [1:0]            output1_modulator,
    input  logic                         weight_we,
    input  logic [1:0]                   neuron_addr,
    input  logic [1:0]                   weight_addr,
    input  logic signed [7:0]            weight_wdata,
    output logic signed [7:0]            weight_rdata,
    output logic                         ready,
    output logic                         busy,
    output logic                         done,
    output logic                         protocol_error,
    output logic [1:0]                   hidden_spikes,
    output logic [1:0]                   output_spikes,
    output logic [1:0]                   pending_hidden_state,
    output logic                         snapshot_valid_state,
    output logic [COMMIT_BITS-1:0]       pending_commit_id_state,
    output logic [EPISODE_BITS-1:0]      pending_episode_id_state,
    output logic                         last_commit_valid_state,
    output logic [COMMIT_BITS-1:0]       last_commit_id_state,
    output logic [31:0]                  weight_epoch_state
);

    typedef enum logic {
        S_IDLE,
        S_WAIT
    } state_t;

    typedef enum logic [2:0] {
        C_NONE,
        C_TICK,
        C_CLEAR,
        C_SNAPSHOT,
        C_MOD,
        C_WEIGHT,
        C_ROUTE_FLUSH
    } command_t;

    state_t state;
    command_t active_command;

    logic [3:0] core_ready;
    logic [3:0] core_done;
    logic [3:0] core_spike;
    logic [3:0] core_snapshot_valid;
    logic [3:0] core_state_clear;
    logic [3:0] core_tick_valid;
    logic [3:0] core_snapshot_we;
    logic [3:0] core_mod_valid;
    logic [3:0] core_weight_we;
    logic [3:0] wait_mask;
    logic [3:0] done_mask;
    logic [3:0] spike_mask;
    logic [3:0] completed_mask;
    logic [3:0] completed_spikes;

    logic [1:0] pending_hidden;
    logic snapshot_valid;
    logic [COMMIT_BITS-1:0] pending_commit_id;
    logic [EPISODE_BITS-1:0] pending_episode_id;
    logic [COMMIT_BITS-1:0] last_commit_id;
    logic last_commit_valid;
    logic [31:0] weight_epoch;
    logic [COMMIT_BITS-1:0] accepted_commit_id;
    logic [EPISODE_BITS-1:0] accepted_episode_id;

    logic signed [7:0] hidden0_weight_rdata;
    logic signed [7:0] hidden1_weight_rdata;
    logic signed [7:0] output0_weight_rdata;
    logic signed [7:0] output1_weight_rdata;

    logic snapshot_allowed;
    logic mod_allowed;
    logic weight_address_valid;

    assign completed_mask = done_mask | (core_done & wait_mask);
    assign completed_spikes = spike_mask | (core_spike & core_done & wait_mask);
    assign ready = (state == S_IDLE) && (&core_ready);
    assign busy = state != S_IDLE;
    assign pending_hidden_state = pending_hidden;
    assign snapshot_valid_state = snapshot_valid;
    assign pending_commit_id_state = pending_commit_id;
    assign pending_episode_id_state = pending_episode_id;
    assign last_commit_valid_state = last_commit_valid;
    assign last_commit_id_state = last_commit_id;
    assign weight_epoch_state = weight_epoch;

    assign snapshot_allowed = learn_enable && !snapshot_valid
        && (!last_commit_valid || (snapshot_commit_id > last_commit_id));
    assign mod_allowed = learn_enable && snapshot_valid
        && (mod_commit_id == pending_commit_id);
    assign weight_address_valid = (neuron_addr < 2)
        || ((weight_addr < 2) && (neuron_addr < 4));

    // 外部只能在 tile 空闲时观察权重，屏蔽各核心完成时间不同造成的中间状态。
    always_comb begin
        weight_rdata = '0;
        if (ready && weight_address_valid) begin
            case (neuron_addr)
                2'd0: weight_rdata = hidden0_weight_rdata;
                2'd1: weight_rdata = hidden1_weight_rdata;
                2'd2: weight_rdata = output0_weight_rdata;
                2'd3: weight_rdata = output1_weight_rdata;
                default: weight_rdata = '0;
            endcase
        end
    end

    // 命令只在 S_IDLE 且四核 ready 时形成一个时钟宽度的核心请求脉冲。
    always_comb begin
        core_state_clear = '0;
        core_tick_valid = '0;
        core_snapshot_we = '0;
        core_mod_valid = '0;
        core_weight_we = '0;

        if (ready) begin
            if (state_clear) begin
                core_state_clear = 4'b1111;
            end else if (snapshot_we) begin
                if (snapshot_allowed)
                    core_snapshot_we = 4'b1111;
            end else if (weight_we) begin
                if (learn_enable && weight_address_valid)
                    core_weight_we[neuron_addr] = 1'b1;
            end else if (mod_valid) begin
                if (mod_allowed)
                    core_mod_valid = 4'b1111;
            end else if (route_flush_valid) begin
                core_tick_valid = 4'b1100;
            end else if (tick_valid) begin
                core_tick_valid = 4'b1111;
            end
        end
    end

`ifdef FORMAL
    // Formal-only protocol guards: rejected or busy transactions cannot reach a core.
    always_comb begin
        if (busy) begin
            assert(core_state_clear == 0);
            assert(core_tick_valid == 0);
            assert(core_snapshot_we == 0);
            assert(core_mod_valid == 0);
            assert(core_weight_we == 0);
        end

        if (ready && !state_clear && snapshot_we && !snapshot_allowed) begin
            assert(core_state_clear == 0);
            assert(core_snapshot_we == 0);
            assert(core_weight_we == 0);
            assert(core_mod_valid == 0);
            assert(core_tick_valid == 0);
        end
        if (ready && !state_clear && !snapshot_we && weight_we
                && (!learn_enable || !weight_address_valid)) begin
            assert(core_state_clear == 0);
            assert(core_snapshot_we == 0);
            assert(core_weight_we == 0);
            assert(core_mod_valid == 0);
            assert(core_tick_valid == 0);
        end
        if (ready && !state_clear && !snapshot_we && !weight_we
                && mod_valid && !mod_allowed) begin
            assert(core_state_clear == 0);
            assert(core_snapshot_we == 0);
            assert(core_weight_we == 0);
            assert(core_mod_valid == 0);
            assert(core_tick_valid == 0);
        end
        if (ready && !state_clear && !snapshot_we && !weight_we
                && !mod_valid && route_flush_valid) begin
            assert(core_state_clear == 0);
            assert(core_snapshot_we == 0);
            assert(core_weight_we == 0);
            assert(core_mod_valid == 0);
            assert(core_tick_valid == 4'b1100);
        end
    end
`endif

    // hidden(0/1) 读取片外 4-bit 输入，阈值 4。
    digital_lif_engine #(.N_INPUTS(4), .THRESHOLD(4)) hidden0 (
        .clk(clk), .rst(rst), .state_clear(core_state_clear[0]),
        .tick_valid(core_tick_valid[0]), .input_spikes(input_spikes),
        .learn_enable(learn_enable), .snapshot_we(core_snapshot_we[0]),
        .mod_valid(core_mod_valid[0]), .modulator(hidden0_modulator),
        .weight_we(core_weight_we[0]), .weight_addr(weight_addr),
        .weight_wdata(weight_wdata), .weight_rdata(hidden0_weight_rdata),
        .ready(core_ready[0]), .done(core_done[0]), .spike(core_spike[0]),
        .membrane(), .threshold_state(), .snapshot_valid_state(core_snapshot_valid[0])
    );

    digital_lif_engine #(.N_INPUTS(4), .THRESHOLD(4)) hidden1 (
        .clk(clk), .rst(rst), .state_clear(core_state_clear[1]),
        .tick_valid(core_tick_valid[1]), .input_spikes(input_spikes),
        .learn_enable(learn_enable), .snapshot_we(core_snapshot_we[1]),
        .mod_valid(core_mod_valid[1]), .modulator(hidden1_modulator),
        .weight_we(core_weight_we[1]), .weight_addr(weight_addr),
        .weight_wdata(weight_wdata), .weight_rdata(hidden1_weight_rdata),
        .ready(core_ready[1]), .done(core_done[1]), .spike(core_spike[1]),
        .membrane(), .threshold_state(), .snapshot_valid_state(core_snapshot_valid[1])
    );

    // output(2/3) 始终读取本次 TICK 接受前的 pending_hidden，保持一逻辑 tick 延迟。
    digital_lif_engine #(.N_INPUTS(2), .THRESHOLD(2)) output0 (
        .clk(clk), .rst(rst), .state_clear(core_state_clear[2]),
        .tick_valid(core_tick_valid[2]), .input_spikes(pending_hidden),
        .learn_enable(learn_enable), .snapshot_we(core_snapshot_we[2]),
        .mod_valid(core_mod_valid[2]), .modulator(output0_modulator),
        .weight_we(core_weight_we[2]), .weight_addr(weight_addr[0]),
        .weight_wdata(weight_wdata), .weight_rdata(output0_weight_rdata),
        .ready(core_ready[2]), .done(core_done[2]), .spike(core_spike[2]),
        .membrane(), .threshold_state(), .snapshot_valid_state(core_snapshot_valid[2])
    );

    digital_lif_engine #(.N_INPUTS(2), .THRESHOLD(2)) output1 (
        .clk(clk), .rst(rst), .state_clear(core_state_clear[3]),
        .tick_valid(core_tick_valid[3]), .input_spikes(pending_hidden),
        .learn_enable(learn_enable), .snapshot_we(core_snapshot_we[3]),
        .mod_valid(core_mod_valid[3]), .modulator(output1_modulator),
        .weight_we(core_weight_we[3]), .weight_addr(weight_addr[0]),
        .weight_wdata(weight_wdata), .weight_rdata(output1_weight_rdata),
        .ready(core_ready[3]), .done(core_done[3]), .spike(core_spike[3]),
        .membrane(), .threshold_state(), .snapshot_valid_state(core_snapshot_valid[3])
    );

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            active_command <= C_NONE;
            wait_mask <= '0;
            done_mask <= '0;
            spike_mask <= '0;
            pending_hidden <= '0;
            snapshot_valid <= 1'b0;
            pending_commit_id <= '0;
            pending_episode_id <= '0;
            last_commit_id <= '0;
            last_commit_valid <= 1'b0;
            weight_epoch <= '0;
            accepted_commit_id <= '0;
            accepted_episode_id <= '0;
            done <= 1'b0;
            protocol_error <= 1'b0;
            hidden_spikes <= '0;
            output_spikes <= '0;
        end else begin
            done <= 1'b0;
            protocol_error <= 1'b0;
            hidden_spikes <= '0;
            output_spikes <= '0;

            case (state)
                S_IDLE: begin
                    done_mask <= '0;
                    spike_mask <= '0;
                    active_command <= C_NONE;
                    if (state_clear && ready) begin
                        active_command <= C_CLEAR;
                        wait_mask <= 4'b1111;
                        state <= S_WAIT;
                    end else if (snapshot_we && ready) begin
                        if (!snapshot_allowed) begin
                            protocol_error <= 1'b1;
                            done <= 1'b1;
                        end else begin
                            accepted_commit_id <= snapshot_commit_id;
                            accepted_episode_id <= snapshot_episode_id;
                            active_command <= C_SNAPSHOT;
                            wait_mask <= 4'b1111;
                            state <= S_WAIT;
                        end
                    end else if (weight_we && ready) begin
                        if (!learn_enable || !weight_address_valid) begin
                            protocol_error <= 1'b1;
                            done <= 1'b1;
                        end else begin
                            active_command <= C_WEIGHT;
                            wait_mask <= 4'b0001 << neuron_addr;
                            state <= S_WAIT;
                        end
                    end else if (mod_valid && ready) begin
                        if (!mod_allowed) begin
                            protocol_error <= 1'b1;
                            done <= 1'b1;
                        end else begin
                            active_command <= C_MOD;
                            wait_mask <= 4'b1111;
                            state <= S_WAIT;
                        end
                    end else if (route_flush_valid && ready) begin
                        active_command <= C_ROUTE_FLUSH;
                        wait_mask <= 4'b1100;
                        state <= S_WAIT;
                    end else if (tick_valid && ready) begin
                        active_command <= C_TICK;
                        wait_mask <= 4'b1111;
                        state <= S_WAIT;
                    end
                end

                S_WAIT: begin
                    done_mask <= completed_mask;
                    spike_mask <= completed_spikes;
                    if ((completed_mask & wait_mask) == wait_mask) begin
                        case (active_command)
                            C_TICK: begin
                                pending_hidden <= completed_spikes[1:0];
                                hidden_spikes <= completed_spikes[1:0];
                                output_spikes <= completed_spikes[3:2];
                            end
                            C_ROUTE_FLUSH: begin
                                pending_hidden <= '0;
                                output_spikes <= completed_spikes[3:2];
                            end
                            C_CLEAR: pending_hidden <= '0;
                            C_SNAPSHOT: begin
                                snapshot_valid <= 1'b1;
                                pending_commit_id <= accepted_commit_id;
                                pending_episode_id <= accepted_episode_id;
                                last_commit_id <= accepted_commit_id;
                                last_commit_valid <= 1'b1;
                            end
                            C_MOD: begin
                                snapshot_valid <= 1'b0;
                                weight_epoch <= weight_epoch + 1'b1;
                            end
                            default: begin end
                        endcase
                        done <= 1'b1;
                        done_mask <= '0;
                        spike_mask <= '0;
                        state <= S_IDLE;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule

// 面向阵列的多周期三因子 LIF 引擎：每周期处理一条突触，避免大组合路径。
module digital_lif_engine #(
    parameter int N_INPUTS = 4,
    parameter int W_BITS = 8,
    parameter int V_BITS = 16,
    parameter int TRACE_BITS = 8,
    parameter int ELIG_BITS = 12,
    parameter int REF_BITS = 4,
    parameter int THRESH_BITS = 8,
    parameter int THRESHOLD = 6,
    parameter int RESET_VALUE = 0,
    parameter int INIT_WEIGHT = 2,
    parameter int REFRACTORY_LENGTH = 1,
    parameter int CURRENT_LEAK_SHIFT = 2,
    parameter int MEMBRANE_LEAK_SHIFT = 2,
    parameter int TRACE_DECAY_SHIFT = 2,
    parameter int ELIGIBILITY_DECAY_SHIFT = 2,
    parameter int LEARNING_SHIFT = 3,
    parameter int TRACE_INCREMENT = 8,
    parameter int A_PLUS = 2,
    parameter int A_MINUS = 2,
    parameter int SILENT_CREDIT_GAIN = 2,
    parameter int THRESHOLD_INCREMENT = 1,
    parameter int THRESHOLD_RELAX_SHIFT = 4,
    parameter int THRESHOLD_MAX = 31,
    parameter int WEIGHT_MIN = -7,
    parameter int WEIGHT_MAX = 7,
    parameter int STATE_MIN = -32768,
    parameter int STATE_MAX = 32767
) (
    input  logic                         clk,
    input  logic                         rst,
    input  logic                         state_clear,
    input  logic                         tick_valid,
    input  logic [N_INPUTS-1:0]          input_spikes,
    input  logic                         learn_enable,
    input  logic                         snapshot_we,
    input  logic                         mod_valid,
    input  logic signed [1:0]            modulator,
    input  logic                         weight_we,
    input  logic [((N_INPUTS <= 1) ? 1 : $clog2(N_INPUTS))-1:0] weight_addr,
    input  logic signed [W_BITS-1:0]     weight_wdata,
    output logic signed [W_BITS-1:0]     weight_rdata,
    output logic                         ready,
    output logic                         done,
    output logic                         spike,
    output logic signed [V_BITS-1:0]     membrane,
    output logic [THRESH_BITS-1:0]       threshold_state,
    output logic                         snapshot_valid_state,
    // 只读导出已提交的 snapshot；lane i 固定映射到 i*ELIG_BITS +: ELIG_BITS。
    output logic [N_INPUTS*ELIG_BITS-1:0] eligibility_snapshot_flat_state
);

    localparam integer signed ELIG_MIN = -(1 <<< (ELIG_BITS - 1));
    localparam integer signed ELIG_MAX = (1 <<< (ELIG_BITS - 1)) - 1;
    localparam integer TRACE_MAX = (1 <<< TRACE_BITS) - 1;
    localparam integer ADDR_BITS = (N_INPUTS <= 1) ? 1 : $clog2(N_INPUTS);
    localparam logic [REF_BITS-1:0] REF_LENGTH_VALUE = REFRACTORY_LENGTH;
    localparam logic [THRESH_BITS-1:0] THRESHOLD_VALUE = THRESHOLD;

    typedef enum logic [3:0] {
        S_IDLE,
        S_TICK_SCAN,
        S_TICK_UPDATE,
        S_CURRENT_SAT,
        S_MEMBRANE_ADD,
        S_TICK_RESOLVE,
        S_POST_SCAN,
        S_TICK_COMMIT,
        S_SNAPSHOT_SCAN,
        S_SNAPSHOT_COMMIT,
        S_MOD_SCAN,
        S_MOD_COMMIT
    } state_t;

    state_t state;
    logic [ADDR_BITS-1:0] scan_index;
    logic [N_INPUTS-1:0] input_latched;
    logic learn_latched;
    logic signed [1:0] modulator_latched;
    logic refractory_latched;

    logic signed [W_BITS-1:0] weights [0:N_INPUTS-1];
    logic signed [W_BITS-1:0] weights_work [0:N_INPUTS-1];
    logic [TRACE_BITS-1:0] pre_trace [0:N_INPUTS-1];
    logic [TRACE_BITS-1:0] pre_trace_work [0:N_INPUTS-1];
    logic signed [ELIG_BITS-1:0] eligibility [0:N_INPUTS-1];
    logic signed [ELIG_BITS-1:0] eligibility_work [0:N_INPUTS-1];
    logic signed [ELIG_BITS-1:0] eligibility_snapshot [0:N_INPUTS-1];
    logic signed [ELIG_BITS-1:0] eligibility_snapshot_work [0:N_INPUTS-1];
    logic snapshot_valid;
    logic [TRACE_BITS-1:0] post_trace;
    logic signed [V_BITS-1:0] current_reg;
    logic signed [V_BITS-1:0] membrane_reg;
    logic [REF_BITS-1:0] refractory;
    logic [THRESH_BITS-1:0] threshold_reg;

    logic signed [31:0] current_acc_work;
    logic signed [W_BITS-1:0] weight_item;
    logic [TRACE_BITS-1:0] pre_decay_item;
    logic signed [ELIG_BITS-1:0] eligibility_decay_item;
    logic synapse_active_item;
    logic signed [V_BITS-1:0] current_result_work;
    logic signed [V_BITS-1:0] membrane_base_work;
    logic signed [V_BITS-1:0] membrane_candidate_work;
    logic signed [V_BITS-1:0] membrane_result_work;
    logic [REF_BITS-1:0] refractory_result_work;
    logic [THRESH_BITS-1:0] threshold_result_work;
    logic [TRACE_BITS-1:0] post_result_work;
    logic spike_pending;
    logic [TRACE_BITS-1:0] post_decay_work;

    integer signed value_acc;
    integer signed trace_acc;
    integer signed eligibility_acc;
    integer signed delta;
    integer signed threshold_acc;
    integer i;

    assign ready = state == S_IDLE;
    assign membrane = membrane_reg;
    assign threshold_state = threshold_reg;
    assign snapshot_valid_state = snapshot_valid;

    generate
        genvar snapshot_export_index;
        for (snapshot_export_index = 0;
             snapshot_export_index < N_INPUTS;
             snapshot_export_index = snapshot_export_index + 1) begin : gen_snapshot_export
            assign eligibility_snapshot_flat_state[
                snapshot_export_index*ELIG_BITS +: ELIG_BITS
            ] = eligibility_snapshot[snapshot_export_index];
        end
    endgenerate

    function automatic logic address_valid(input logic [ADDR_BITS-1:0] address);
        logic [ADDR_BITS:0] extended_address;
        logic [ADDR_BITS:0] input_count;
        begin
            extended_address = {1'b0, address};
            input_count = N_INPUTS;
            address_valid = extended_address < input_count;
        end
    endfunction

    always_comb begin
        if (address_valid(weight_addr))
            weight_rdata = weights[weight_addr];
        else
            weight_rdata = '0;
    end

    function automatic integer signed decay_toward_zero(
        input integer signed value,
        input integer shift
    );
        integer signed magnitude;
        integer signed decay_amount;
        integer signed next_magnitude;
        begin
            if ((value == 0) || (shift < 0)) begin
                decay_toward_zero = value;
            end else begin
                magnitude = value < 0 ? -value : value;
                decay_amount = magnitude >>> shift;
                if (decay_amount < 1)
                    decay_amount = 1;
                next_magnitude = magnitude - decay_amount;
                if (next_magnitude < 0)
                    next_magnitude = 0;
                decay_toward_zero = value < 0 ? -next_magnitude : next_magnitude;
            end
        end
    endfunction

    function automatic [TRACE_BITS-1:0] decay_trace_value(
        input logic [TRACE_BITS-1:0] value
    );
        logic [TRACE_BITS-1:0] decay_amount;
        begin
            if (value == 0) begin
                decay_trace_value = '0;
            end else begin
                decay_amount = value >> TRACE_DECAY_SHIFT;
                if (decay_amount == 0)
                    decay_amount = {{(TRACE_BITS-1){1'b0}}, 1'b1};
                decay_trace_value = value - decay_amount;
            end
        end
    endfunction

    function automatic signed [V_BITS-1:0] decay_state_value(
        input logic signed [V_BITS-1:0] value,
        input integer shift
    );
        logic signed [V_BITS:0] extended_value;
        logic signed [V_BITS:0] signed_result;
        logic [V_BITS:0] magnitude;
        logic [V_BITS:0] decay_amount;
        logic [V_BITS:0] next_magnitude;
        begin
            extended_value = value;
            if ((value == 0) || (shift < 0)) begin
                decay_state_value = value;
            end else begin
                magnitude = value < 0 ? -extended_value : extended_value;
                decay_amount = magnitude >> shift;
                if (decay_amount == 0)
                    decay_amount = {{V_BITS{1'b0}}, 1'b1};
                next_magnitude = magnitude - decay_amount;
                signed_result = value < 0 ? -$signed(next_magnitude) : $signed(next_magnitude);
                decay_state_value = signed_result[V_BITS-1:0];
            end
        end
    endfunction

    function automatic signed [ELIG_BITS-1:0] decay_eligibility_value(
        input logic signed [ELIG_BITS-1:0] value
    );
        logic signed [ELIG_BITS:0] extended_value;
        logic signed [ELIG_BITS:0] signed_result;
        logic [ELIG_BITS:0] magnitude;
        logic [ELIG_BITS:0] decay_amount;
        logic [ELIG_BITS:0] next_magnitude;
        begin
            extended_value = value;
            if (value == 0) begin
                decay_eligibility_value = '0;
            end else begin
                magnitude = value < 0 ? -extended_value : extended_value;
                decay_amount = magnitude >> ELIGIBILITY_DECAY_SHIFT;
                if (decay_amount == 0)
                    decay_amount = {{ELIG_BITS{1'b0}}, 1'b1};
                next_magnitude = magnitude - decay_amount;
                signed_result = value < 0 ? -$signed(next_magnitude) : $signed(next_magnitude);
                decay_eligibility_value = signed_result[ELIG_BITS-1:0];
            end
        end
    endfunction

    function automatic signed [V_BITS-1:0] sat_state(input integer signed value);
        begin
            if (value > STATE_MAX)
                sat_state = STATE_MAX[V_BITS-1:0];
            else if (value < STATE_MIN)
                sat_state = STATE_MIN[V_BITS-1:0];
            else
                sat_state = value[V_BITS-1:0];
        end
    endfunction

    function automatic [TRACE_BITS-1:0] sat_trace(input integer signed value);
        begin
            if (value > TRACE_MAX)
                sat_trace = TRACE_MAX[TRACE_BITS-1:0];
            else if (value < 0)
                sat_trace = '0;
            else
                sat_trace = value[TRACE_BITS-1:0];
        end
    endfunction

    function automatic signed [ELIG_BITS-1:0] sat_eligibility(input integer signed value);
        begin
            if (value > ELIG_MAX)
                sat_eligibility = ELIG_MAX[ELIG_BITS-1:0];
            else if (value < ELIG_MIN)
                sat_eligibility = ELIG_MIN[ELIG_BITS-1:0];
            else
                sat_eligibility = value[ELIG_BITS-1:0];
        end
    endfunction

    function automatic signed [W_BITS-1:0] sat_weight(input integer signed value);
        begin
            if (value > WEIGHT_MAX)
                sat_weight = WEIGHT_MAX[W_BITS-1:0];
            else if (value < WEIGHT_MIN)
                sat_weight = WEIGHT_MIN[W_BITS-1:0];
            else
                sat_weight = value[W_BITS-1:0];
        end
    endfunction

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            scan_index <= '0;
            input_latched <= '0;
            learn_latched <= 1'b0;
            modulator_latched <= '0;
            refractory_latched <= 1'b0;
            current_reg <= RESET_VALUE[V_BITS-1:0];
            membrane_reg <= RESET_VALUE[V_BITS-1:0];
            refractory <= '0;
            threshold_reg <= THRESHOLD_VALUE;
            post_trace <= '0;
            current_acc_work <= RESET_VALUE;
            weight_item <= '0;
            pre_decay_item <= '0;
            eligibility_decay_item <= '0;
            synapse_active_item <= 1'b0;
            current_result_work <= RESET_VALUE[V_BITS-1:0];
            membrane_base_work <= RESET_VALUE[V_BITS-1:0];
            membrane_candidate_work <= RESET_VALUE[V_BITS-1:0];
            membrane_result_work <= RESET_VALUE[V_BITS-1:0];
            refractory_result_work <= '0;
            threshold_result_work <= THRESHOLD_VALUE;
            post_result_work <= '0;
            spike_pending <= 1'b0;
            post_decay_work <= '0;
            snapshot_valid <= 1'b0;
            done <= 1'b0;
            spike <= 1'b0;
            for (i = 0; i < N_INPUTS; i = i + 1) begin
                weights[i] <= INIT_WEIGHT[W_BITS-1:0];
                weights_work[i] <= INIT_WEIGHT[W_BITS-1:0];
                pre_trace[i] <= '0;
                pre_trace_work[i] <= '0;
                eligibility[i] <= '0;
                eligibility_work[i] <= '0;
                eligibility_snapshot[i] <= '0;
                eligibility_snapshot_work[i] <= '0;
            end
        end else begin
            done <= 1'b0;
            spike <= 1'b0;

            case (state)
                S_IDLE: begin
                    if (state_clear) begin
                        current_reg <= RESET_VALUE[V_BITS-1:0];
                        membrane_reg <= RESET_VALUE[V_BITS-1:0];
                        refractory <= '0;
                        threshold_reg <= THRESHOLD_VALUE;
                        post_trace <= '0;
                        for (i = 0; i < N_INPUTS; i = i + 1) begin
                            pre_trace[i] <= '0;
                            eligibility[i] <= '0;
                        end
                        done <= 1'b1;
                    end else if (snapshot_we) begin
                        scan_index <= '0;
                        state <= S_SNAPSHOT_SCAN;
                    end else if (weight_we) begin
                        if (learn_enable && address_valid(weight_addr))
                            weights[weight_addr] <= sat_weight($signed(weight_wdata));
                        done <= 1'b1;
                    end else if (mod_valid) begin
                        // 推理模式和零调制都是已接受的 no-op，不能让请求方死锁。
                        if (!learn_enable || (modulator == 0)) begin
                            done <= 1'b1;
                        end else begin
                            scan_index <= '0;
                            modulator_latched <= modulator;
                            state <= S_MOD_SCAN;
                        end
                    end else if (tick_valid) begin
                        input_latched <= input_spikes;
                        learn_latched <= learn_enable;
                        refractory_latched <= refractory != 0;
                        current_acc_work <= decay_state_value(
                            current_reg,
                            CURRENT_LEAK_SHIFT
                        );
                        membrane_base_work <= decay_state_value(
                            membrane_reg,
                            MEMBRANE_LEAK_SHIFT
                        );
                        if (learn_enable) begin
                            post_decay_work <= decay_trace_value(post_trace);
                        end else begin
                            post_decay_work <= post_trace;
                        end
                        scan_index <= '0;
                        spike_pending <= 1'b0;
                        state <= S_TICK_SCAN;
                    end
                end

                S_TICK_SCAN: begin
                    // 第一拍只读当前突触并完成衰减，切断地址选择到资格迹线写回的长路径。
                    weight_item <= weights[scan_index];
                    synapse_active_item <= !refractory_latched && input_latched[scan_index];
                    if (learn_latched) begin
                        pre_decay_item <= decay_trace_value(pre_trace[scan_index]);
                        eligibility_decay_item <= decay_eligibility_value(
                            eligibility[scan_index]
                        );
                    end
                    state <= S_TICK_UPDATE;
                end

                S_TICK_UPDATE: begin
                    // 第二拍使用已寄存的单突触数据，更新事务私有工作区。
                    if (synapse_active_item) begin
                        value_acc = current_acc_work + $signed(weight_item);
                        current_acc_work <= value_acc;
                    end

                    if (learn_latched) begin
                        trace_acc = $unsigned(pre_decay_item);
                        eligibility_acc = $signed(eligibility_decay_item);
                        if (synapse_active_item) begin
                            trace_acc = trace_acc + TRACE_INCREMENT;
                            trace_acc = sat_trace(trace_acc);
                            eligibility_acc = eligibility_acc
                                + (trace_acc * SILENT_CREDIT_GAIN)
                                - ($unsigned(post_decay_work) * A_MINUS);
                        end
                        pre_trace_work[scan_index] <= sat_trace(trace_acc);
                        eligibility_work[scan_index] <= sat_eligibility(eligibility_acc);
                    end

                    if (scan_index == N_INPUTS - 1) begin
                        state <= S_CURRENT_SAT;
                    end else begin
                        scan_index <= scan_index + 1'b1;
                        state <= S_TICK_SCAN;
                    end
                end

                S_CURRENT_SAT: begin
                    // 单独寄存 32 位累计的饱和结果，避免与膜电位和发放决策串成一拍。
                    current_result_work <= sat_state(current_acc_work);
                    state <= S_MEMBRANE_ADD;
                end

                S_MEMBRANE_ADD: begin
                    value_acc = $signed(membrane_base_work) + $signed(current_result_work);
                    membrane_candidate_work <= sat_state(value_acc);
                    state <= S_TICK_RESOLVE;
                end

                S_TICK_RESOLVE: begin
                    if (refractory_latched) begin
                        membrane_result_work <= RESET_VALUE[V_BITS-1:0];
                        refractory_result_work <= refractory - 1'b1;
                        spike_pending <= 1'b0;
                        if (learn_latched) begin
                            post_result_work <= post_decay_work;
                            threshold_result_work <= threshold_reg;
                            if ($unsigned(threshold_reg) > THRESHOLD) begin
                                threshold_acc = $unsigned(threshold_reg) - THRESHOLD;
                                threshold_acc = threshold_acc >>> THRESHOLD_RELAX_SHIFT;
                                if (threshold_acc < 1)
                                    threshold_acc = 1;
                                threshold_result_work <= $unsigned(threshold_reg) - threshold_acc;
                            end
                        end else begin
                            post_result_work <= post_trace;
                            threshold_result_work <= threshold_reg;
                        end
                        state <= S_TICK_COMMIT;
                    end else if (membrane_candidate_work >= $signed({1'b0, threshold_reg})) begin
                        membrane_result_work <= RESET_VALUE[V_BITS-1:0];
                        refractory_result_work <= REF_LENGTH_VALUE;
                        spike_pending <= 1'b1;
                        if (learn_latched) begin
                            trace_acc = $unsigned(post_decay_work) + TRACE_INCREMENT;
                            post_result_work <= sat_trace(trace_acc);
                            threshold_acc = $unsigned(threshold_reg) + THRESHOLD_INCREMENT;
                            if (threshold_acc > THRESHOLD_MAX)
                                threshold_acc = THRESHOLD_MAX;
                            threshold_result_work <= threshold_acc[THRESH_BITS-1:0];
                            scan_index <= '0;
                            state <= S_POST_SCAN;
                        end else begin
                            post_result_work <= post_trace;
                            threshold_result_work <= threshold_reg;
                            state <= S_TICK_COMMIT;
                        end
                    end else begin
                        membrane_result_work <= membrane_candidate_work;
                        refractory_result_work <= refractory;
                        spike_pending <= 1'b0;
                        if (learn_latched) begin
                            post_result_work <= post_decay_work;
                            threshold_result_work <= threshold_reg;
                            if ($unsigned(threshold_reg) > THRESHOLD) begin
                                threshold_acc = $unsigned(threshold_reg) - THRESHOLD;
                                threshold_acc = threshold_acc >>> THRESHOLD_RELAX_SHIFT;
                                if (threshold_acc < 1)
                                    threshold_acc = 1;
                                threshold_result_work <= $unsigned(threshold_reg) - threshold_acc;
                            end
                        end else begin
                            post_result_work <= post_trace;
                            threshold_result_work <= threshold_reg;
                        end
                        state <= S_TICK_COMMIT;
                    end
                end

                S_POST_SCAN: begin
                    eligibility_acc = $signed(eligibility_work[scan_index]);
                    eligibility_acc = eligibility_acc
                        + (A_PLUS * $unsigned(pre_trace_work[scan_index]));
                    eligibility_work[scan_index] <= sat_eligibility(eligibility_acc);
                    if (scan_index == N_INPUTS - 1) begin
                        state <= S_TICK_COMMIT;
                    end else begin
                        scan_index <= scan_index + 1'b1;
                    end
                end

                S_TICK_COMMIT: begin
                    current_reg <= current_result_work;
                    membrane_reg <= membrane_result_work;
                    refractory <= refractory_result_work;
                    threshold_reg <= threshold_result_work;
                    post_trace <= post_result_work;
                    if (learn_latched) begin
                        for (i = 0; i < N_INPUTS; i = i + 1) begin
                            pre_trace[i] <= pre_trace_work[i];
                            eligibility[i] <= eligibility_work[i];
                        end
                    end
                    spike <= spike_pending;
                    done <= 1'b1;
                    state <= S_IDLE;
                end

                S_SNAPSHOT_SCAN: begin
                    eligibility_snapshot_work[scan_index] <= eligibility[scan_index];
                    if (scan_index == N_INPUTS - 1) begin
                        state <= S_SNAPSHOT_COMMIT;
                    end else begin
                        scan_index <= scan_index + 1'b1;
                    end
                end

                S_SNAPSHOT_COMMIT: begin
                    for (i = 0; i < N_INPUTS; i = i + 1)
                        eligibility_snapshot[i] <= eligibility_snapshot_work[i];
                    snapshot_valid <= 1'b1;
                    done <= 1'b1;
                    state <= S_IDLE;
                end

                S_MOD_SCAN: begin
                    if (snapshot_valid)
                        eligibility_acc = $signed(eligibility_snapshot[scan_index]);
                    else
                        eligibility_acc = $signed(eligibility[scan_index]);
                    value_acc = $signed(modulator_latched);
                    delta = value_acc * eligibility_acc;
                    delta = delta >>> LEARNING_SHIFT;
                    value_acc = $signed(weights[scan_index]) + delta;
                    weights_work[scan_index] <= sat_weight(value_acc);
                    if (scan_index == N_INPUTS - 1) begin
                        state <= S_MOD_COMMIT;
                    end else begin
                        scan_index <= scan_index + 1'b1;
                    end
                end

                S_MOD_COMMIT: begin
                    for (i = 0; i < N_INPUTS; i = i + 1)
                        weights[i] <= weights_work[i];
                    snapshot_valid <= 1'b0;
                    done <= 1'b1;
                    state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end
endmodule

// V1 数字三因子 LIF：唯一 next-state、有符号饱和、推理冻结学习状态。
module digital_lif_core #(
    parameter int N_INPUTS = 4,
    parameter int ADDR_BITS = 2,
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
    input  logic                         mod_valid,
    input  logic signed [1:0]            modulator,
    input  logic                         snapshot_we,
    input  logic                         weight_we,
    input  logic [ADDR_BITS-1:0]         weight_addr,
    input  logic signed [W_BITS-1:0]     weight_wdata,
    output logic signed [W_BITS-1:0]     weight_rdata,
    output logic                         spike,
    output logic signed [V_BITS-1:0]     membrane,
    output logic [THRESH_BITS-1:0]       threshold_state,
    output logic                         ready
);

    localparam integer signed ELIG_MIN = -(1 <<< (ELIG_BITS - 1));
    localparam integer signed ELIG_MAX = (1 <<< (ELIG_BITS - 1)) - 1;
    localparam integer TRACE_MAX = (1 <<< TRACE_BITS) - 1;
    localparam logic [REF_BITS-1:0] REF_LENGTH_VALUE = REFRACTORY_LENGTH;
    localparam logic [THRESH_BITS-1:0] THRESHOLD_VALUE = THRESHOLD;

    logic signed [W_BITS-1:0] weights [0:N_INPUTS-1];
    logic signed [W_BITS-1:0] weights_next [0:N_INPUTS-1];
    logic [TRACE_BITS-1:0] pre_trace [0:N_INPUTS-1];
    logic [TRACE_BITS-1:0] pre_trace_next [0:N_INPUTS-1];
    logic signed [ELIG_BITS-1:0] eligibility [0:N_INPUTS-1];
    logic signed [ELIG_BITS-1:0] eligibility_next [0:N_INPUTS-1];
    logic signed [ELIG_BITS-1:0] eligibility_snapshot [0:N_INPUTS-1];
    logic signed [ELIG_BITS-1:0] eligibility_snapshot_next [0:N_INPUTS-1];
    logic snapshot_valid;
    logic snapshot_valid_next;
    logic [TRACE_BITS-1:0] post_trace;
    logic [TRACE_BITS-1:0] post_trace_next;
    logic signed [V_BITS-1:0] current_reg;
    logic signed [V_BITS-1:0] current_next;
    logic signed [V_BITS-1:0] membrane_reg;
    logic signed [V_BITS-1:0] membrane_next;
    logic signed [V_BITS-1:0] membrane_candidate;
    logic [REF_BITS-1:0] refractory;
    logic [REF_BITS-1:0] refractory_next;
    logic [THRESH_BITS-1:0] threshold_reg;
    logic [THRESH_BITS-1:0] threshold_next;
    logic spike_next;

    integer signed current_acc;
    integer signed membrane_acc;
    integer signed trace_acc;
    integer signed eligibility_acc;
    integer signed weight_acc;
    integer signed delta;
    integer signed threshold_acc;
    integer signed decrement;
    integer signed trace_value;
    integer signed post_trace_value;
    integer signed modulator_value;
    integer signed weight_value;
    integer signed threshold_value;
    integer i;
    integer j;

    assign membrane = membrane_reg;
    assign threshold_state = threshold_reg;
    assign ready = 1'b1;
    always_comb begin
        if (address_valid(weight_addr))
            weight_rdata = weights[weight_addr];
        else
            weight_rdata = '0;
    end

    function automatic address_valid(input logic [ADDR_BITS-1:0] value);
        integer unsigned address_as_int;
        begin
            address_as_int = value;
            address_valid = address_as_int < N_INPUTS;
        end
    endfunction

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

    always_comb begin
        current_next = current_reg;
        membrane_next = membrane_reg;
        membrane_candidate = membrane_reg;
        refractory_next = refractory;
        threshold_next = threshold_reg;
        post_trace_next = post_trace;
        snapshot_valid_next = snapshot_valid;
        spike_next = 1'b0;
        current_acc = 0;
        membrane_acc = 0;
        trace_acc = 0;
        eligibility_acc = 0;
        weight_acc = 0;
        delta = 0;
        threshold_acc = 0;
        decrement = 0;
        trace_value = 0;
        post_trace_value = 0;
        modulator_value = 0;
        weight_value = 0;
        threshold_value = 0;

        for (i = 0; i < N_INPUTS; i = i + 1) begin
            weights_next[i] = weights[i];
            pre_trace_next[i] = pre_trace[i];
            eligibility_next[i] = eligibility[i];
            eligibility_snapshot_next[i] = eligibility_snapshot[i];
        end

        if (tick_valid) begin
            current_acc = $signed(current_reg);
            current_acc = decay_toward_zero(current_acc, CURRENT_LEAK_SHIFT);
            if (refractory == 0) begin
                for (i = 0; i < N_INPUTS; i = i + 1) begin
                    if (input_spikes[i]) begin
                        weight_value = $signed(weights[i]);
                        current_acc = current_acc + weight_value;
                    end
                end
            end
            current_next = sat_state(current_acc);

            membrane_acc = $signed(membrane_reg);
            membrane_acc = decay_toward_zero(membrane_acc, MEMBRANE_LEAK_SHIFT);
            weight_value = $signed(current_next);
            membrane_acc = membrane_acc + weight_value;
            membrane_candidate = sat_state(membrane_acc);
            membrane_next = membrane_candidate;

            if (refractory != 0) begin
                refractory_next = refractory - 1'b1;
                membrane_next = RESET_VALUE;
            end else if ($signed(membrane_candidate) >= THRESHOLD) begin
                spike_next = 1'b1;
                membrane_next = RESET_VALUE[V_BITS-1:0];
                refractory_next = REF_LENGTH_VALUE;
            end

            if (learn_enable) begin
                trace_value = $unsigned(post_trace);
                trace_value = decay_toward_zero(trace_value, TRACE_DECAY_SHIFT);
                post_trace_next = sat_trace(trace_value);
                for (i = 0; i < N_INPUTS; i = i + 1) begin
                    trace_value = $unsigned(pre_trace[i]);
                    trace_value = decay_toward_zero(trace_value, TRACE_DECAY_SHIFT);
                    pre_trace_next[i] = sat_trace(trace_value);
                    eligibility_acc = $signed(eligibility[i]);
                    eligibility_acc = decay_toward_zero(eligibility_acc, ELIGIBILITY_DECAY_SHIFT);
                    eligibility_next[i] = sat_eligibility(eligibility_acc);
                end

                if (refractory == 0) begin
                    for (i = 0; i < N_INPUTS; i = i + 1) begin
                        if (input_spikes[i]) begin
                            trace_acc = $unsigned(pre_trace_next[i]) + TRACE_INCREMENT;
                            pre_trace_next[i] = sat_trace(trace_acc);
                            trace_value = $unsigned(pre_trace_next[i]);
                            post_trace_value = $unsigned(post_trace_next);
                            eligibility_acc = $signed(eligibility_next[i]);
                            eligibility_acc = eligibility_acc
                                + (trace_value * SILENT_CREDIT_GAIN)
                                - (post_trace_value * A_MINUS);
                            eligibility_next[i] = sat_eligibility(eligibility_acc);
                        end
                    end
                end

                if (spike_next) begin
                    for (i = 0; i < N_INPUTS; i = i + 1) begin
                        trace_value = $unsigned(pre_trace_next[i]);
                        eligibility_acc = $signed(eligibility_next[i]);
                        eligibility_acc = eligibility_acc + (A_PLUS * trace_value);
                        eligibility_next[i] = sat_eligibility(eligibility_acc);
                    end
                    trace_acc = $unsigned(post_trace_next) + TRACE_INCREMENT;
                    post_trace_next = sat_trace(trace_acc);
                    threshold_value = $unsigned(threshold_reg);
                    threshold_acc = threshold_value + THRESHOLD_INCREMENT;
                    if (threshold_acc > THRESHOLD_MAX)
                        threshold_acc = THRESHOLD_MAX;
                    threshold_next = threshold_acc;
                end

                threshold_value = $unsigned(threshold_next);
                if (!spike_next && (threshold_value > THRESHOLD)) begin
                    decrement = (threshold_value - THRESHOLD) >>> THRESHOLD_RELAX_SHIFT;
                    if (decrement < 1)
                        decrement = 1;
                    threshold_acc = threshold_value - decrement;
                    if (threshold_acc < THRESHOLD)
                        threshold_acc = THRESHOLD;
                    threshold_next = threshold_acc;
                end
            end
        end

        if (snapshot_we) begin
            snapshot_valid_next = 1'b1;
            for (i = 0; i < N_INPUTS; i = i + 1)
                eligibility_snapshot_next[i] = eligibility_next[i];
        end

        // 同 tick 调制使用 eligibility_next；无 tick 时等同于当前 eligibility。
        if (mod_valid && learn_enable) begin
            modulator_value = $signed(modulator);
            for (i = 0; i < N_INPUTS; i = i + 1) begin
                if (snapshot_valid_next)
                    eligibility_acc = $signed(eligibility_snapshot_next[i]);
                else
                    eligibility_acc = $signed(eligibility_next[i]);
                delta = modulator_value * eligibility_acc;
                delta = delta >>> LEARNING_SHIFT;
                weight_acc = $signed(weights[i]);
                weight_acc = weight_acc + delta;
                weights_next[i] = sat_weight(weight_acc);
            end
            snapshot_valid_next = 1'b0;
        end

        // 显式状态端口优先于同周期可塑性提交，INFER 下禁止所有权重写回。
        if (weight_we && learn_enable && address_valid(weight_addr)) begin
            weight_value = $signed(weight_wdata);
            weights_next[weight_addr] = sat_weight(weight_value);
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            current_reg <= RESET_VALUE[V_BITS-1:0];
            membrane_reg <= RESET_VALUE[V_BITS-1:0];
            refractory <= '0;
            threshold_reg <= THRESHOLD_VALUE;
            post_trace <= '0;
            spike <= 1'b0;
            for (j = 0; j < N_INPUTS; j = j + 1) begin
                weights[j] <= INIT_WEIGHT[W_BITS-1:0];
                pre_trace[j] <= '0;
                eligibility[j] <= '0;
                eligibility_snapshot[j] <= '0;
            end
            snapshot_valid <= 1'b0;
        end else if (state_clear) begin
            current_reg <= RESET_VALUE[V_BITS-1:0];
            membrane_reg <= RESET_VALUE[V_BITS-1:0];
            refractory <= '0;
            threshold_reg <= THRESHOLD_VALUE;
            post_trace <= '0;
            spike <= 1'b0;
            for (j = 0; j < N_INPUTS; j = j + 1) begin
                pre_trace[j] <= '0;
                eligibility[j] <= '0;
            end
        end else begin
            current_reg <= current_next;
            membrane_reg <= membrane_next;
            refractory <= refractory_next;
            threshold_reg <= threshold_next;
            post_trace <= post_trace_next;
            spike <= spike_next;
            for (j = 0; j < N_INPUTS; j = j + 1) begin
                weights[j] <= weights_next[j];
                pre_trace[j] <= pre_trace_next[j];
                eligibility[j] <= eligibility_next[j];
                eligibility_snapshot[j] <= eligibility_snapshot_next[j];
            end
            snapshot_valid <= snapshot_valid_next;
        end
    end
endmodule

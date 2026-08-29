// 固定 4->8->2 网络的单 TICK 调度与一拍 detector 路由。
//
// 八个隐藏核心和两个输出核心必须在同一接受边沿启动。输出核心只读取
// 上一次已完成 TICK 保存的 pending_hidden，因此不存在本拍隐藏结果到
// 本拍输出输入的组合穿透。各核心响应允许错拍到达，由 sticky done 汇合。
module pruned_network_tick_scheduler (
    input  logic                         clk,
    input  logic                         rst,

    input  logic                         tick_valid,
    output logic                         tick_ready,
    input  logic                         flush_valid,
    output logic                         flush_ready,
    input  logic [3:0]                   input_spikes,
    input  logic [7:0]                   hidden_train_post,
    input  logic [1:0]                   output_train_post,
    output logic                         rsp_valid,
    input  logic                         rsp_ready,
    output logic [2:0]                   rsp_status,
    output logic [7:0]                   hidden_spikes,
    output logic [1:0]                   output_spikes,
    output logic [7:0]                   pending_hidden_state,

    output logic [7:0]                   hidden_cmd_valid,
    input  logic [7:0]                   hidden_cmd_ready,
    output logic [31:0]                  hidden_input_spikes_flat,
    output logic [7:0]                   hidden_train_post_out,
    output logic [1:0]                   output_cmd_valid,
    input  logic [1:0]                   output_cmd_ready,
    output logic [7:0]                   output_input_spikes_flat,
    output logic [1:0]                   output_train_post_out,

    input  logic [7:0]                   hidden_rsp_valid,
    output logic [7:0]                   hidden_rsp_ready,
    input  logic [7:0]                   hidden_rsp_spike,
    input  logic [23:0]                  hidden_rsp_status_flat,
    input  logic [1:0]                   output_rsp_valid,
    output logic [1:0]                   output_rsp_ready,
    input  logic [1:0]                   output_rsp_spike,
    input  logic [5:0]                   output_rsp_status_flat,

    output logic                         busy,
    output logic                         protocol_error
);

    localparam logic [2:0] ST_OK       = 3'd0;
    localparam logic [2:0] ST_INTERNAL = 3'd1;

    typedef enum logic [1:0] {
        S_IDLE,
        S_WAIT,
        S_RSP
    } state_t;

    state_t state;
    logic [7:0] pending_hidden;
    logic [7:0] hidden_seen;
    logic [1:0] output_seen;
    logic [7:0] hidden_spike_accum;
    logic [1:0] output_spike_accum;
    logic active_flush;
    logic response_error;
    logic current_response_error;
    logic [7:0] hidden_spike_next;
    logic [1:0] output_spike_next;
    wire [7:0] hidden_accept = hidden_rsp_valid & hidden_rsp_ready;
    wire [1:0] output_accept = output_rsp_valid & output_rsp_ready;
    wire [7:0] hidden_seen_next = hidden_seen | hidden_accept;
    wire [1:0] output_seen_next = output_seen | output_accept;
    wire all_cores_ready = (&hidden_cmd_ready) && (&output_cmd_ready);

    assign tick_ready = (state == S_IDLE) && !flush_valid && all_cores_ready;
    assign flush_ready = (state == S_IDLE) && (&output_cmd_ready);
    assign rsp_valid = (state == S_RSP);
    assign rsp_status = response_error ? ST_INTERNAL : ST_OK;
    assign pending_hidden_state = pending_hidden;
    assign busy = (state != S_IDLE);
    assign protocol_error = response_error;
    assign hidden_train_post_out = hidden_train_post;
    assign output_train_post_out = output_train_post;
    assign output_input_spikes_flat = pending_hidden;

    genvar input_index;
    generate
        for (input_index = 0; input_index < 8; input_index = input_index + 1) begin
            assign hidden_input_spikes_flat[input_index*4 +: 4] = input_spikes;
        end
    endgenerate

    always_comb begin
        hidden_cmd_valid = '0;
        output_cmd_valid = '0;
        hidden_rsp_ready = '0;
        output_rsp_ready = '0;

        if ((state == S_IDLE) && flush_valid && (&output_cmd_ready)) begin
            output_cmd_valid = 2'b11;
        end else if ((state == S_IDLE) && tick_valid && all_cores_ready) begin
            hidden_cmd_valid = 8'hff;
            output_cmd_valid = 2'b11;
        end
        if (state == S_WAIT) begin
            hidden_rsp_ready = active_flush ? 8'h00 : ~hidden_seen;
            output_rsp_ready = ~output_seen;
        end
    end

    integer response_index;
    always_comb begin
        hidden_spike_next = hidden_spike_accum;
        output_spike_next = output_spike_accum;
        current_response_error = 1'b0;
        for (response_index = 0; response_index < 8;
                response_index = response_index + 1) begin
            if (hidden_accept[response_index]) begin
                hidden_spike_next[response_index] = hidden_rsp_spike[response_index];
                if (hidden_rsp_status_flat[response_index*3 +: 3] != ST_OK)
                    current_response_error = 1'b1;
            end
        end
        for (response_index = 0; response_index < 2;
                response_index = response_index + 1) begin
            if (output_accept[response_index]) begin
                output_spike_next[response_index] = output_rsp_spike[response_index];
                if (output_rsp_status_flat[response_index*3 +: 3] != ST_OK)
                    current_response_error = 1'b1;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            pending_hidden <= '0;
            hidden_seen <= '0;
            output_seen <= '0;
            hidden_spike_accum <= '0;
            output_spike_accum <= '0;
            hidden_spikes <= '0;
            output_spikes <= '0;
            active_flush <= 1'b0;
            response_error <= 1'b0;
        end else begin
            case (state)
                S_IDLE: begin
                    if (flush_valid && flush_ready) begin
                        hidden_seen <= 8'hff;
                        output_seen <= '0;
                        hidden_spike_accum <= '0;
                        output_spike_accum <= '0;
                        active_flush <= 1'b1;
                        response_error <= 1'b0;
                        state <= S_WAIT;
                    end else if (tick_valid && tick_ready) begin
                        hidden_seen <= '0;
                        output_seen <= '0;
                        hidden_spike_accum <= '0;
                        output_spike_accum <= '0;
                        active_flush <= 1'b0;
                        response_error <= 1'b0;
                        state <= S_WAIT;
                    end
                end

                S_WAIT: begin
                    hidden_seen <= hidden_seen_next;
                    output_seen <= output_seen_next;
                    hidden_spike_accum <= hidden_spike_next;
                    output_spike_accum <= output_spike_next;
                    response_error <= response_error | current_response_error;
                    if ((&hidden_seen_next) && (&output_seen_next)) begin
                        hidden_spikes <= active_flush ? 8'h00 : hidden_spike_next;
                        output_spikes <= output_spike_next;
                        pending_hidden <= active_flush ? 8'h00 : hidden_spike_next;
                        state <= S_RSP;
                    end
                end

                S_RSP: begin
                    if (rsp_ready)
                        state <= S_IDLE;
                end

                default: begin
                    response_error <= 1'b1;
                    state <= S_RSP;
                end
            endcase
        end
    end

endmodule

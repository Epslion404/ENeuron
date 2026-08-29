// 多个四输入剪枝 gate 的网络级原子提交屏障。
//
// 屏障先检查全部 gate 和核心清理端口；任何参与者未就绪时整笔拒绝，
// 不允许部分 gate 启动。后续状态会汇合 gate commit 与 STATE_CLEAR 响应。
module local_prune_commit_barrier #(
    parameter integer N_GATES = 10
) (
    input  logic                         clk,
    input  logic                         rst,

    input  logic                         commit_valid,
    output logic                         commit_ready,
    input  logic [15:0]                  commit_id,
    input  logic                         safe_boundary,
    output logic                         rsp_valid,
    input  logic                         rsp_ready,
    output logic [2:0]                   rsp_status,
    output logic [15:0]                  rsp_id,
    output logic [N_GATES*4-1:0]         rsp_masks_flat,

    output logic [N_GATES-1:0]           gate_cmd_valid,
    input  logic [N_GATES-1:0]           gate_cmd_ready,
    output logic [15:0]                  gate_cmd_id,
    input  logic [N_GATES-1:0]           gate_rsp_valid,
    output logic [N_GATES-1:0]           gate_rsp_ready,
    input  logic [N_GATES*3-1:0]         gate_rsp_status_flat,
    input  logic [N_GATES*4-1:0]         gate_rsp_masks_flat,

    output logic [N_GATES-1:0]           clear_cmd_valid,
    input  logic [N_GATES-1:0]           clear_cmd_ready,
    input  logic [N_GATES-1:0]           clear_rsp_valid,
    output logic [N_GATES-1:0]           clear_rsp_ready,
    input  logic [N_GATES*3-1:0]         clear_rsp_status_flat,

    output logic                         runtime_blocked,
    output logic                         internal_error,
    output logic [31:0]                  commit_epoch_state
);

    localparam logic [2:0] ST_OK       = 3'd0;
    localparam logic [2:0] ST_UNSAFE   = 3'd1;
    localparam logic [2:0] ST_INTERNAL = 3'd2;

    typedef enum logic [2:0] {
        S_IDLE,
        S_WAIT_GATE,
        S_ISSUE_CLEAR,
        S_WAIT_CLEAR,
        S_RSP,
        S_HALT
    } state_t;

    state_t state;
    logic [15:0] active_commit_id;
    logic [2:0] response_status;
    logic [N_GATES*4-1:0] response_masks;
    logic [31:0] commit_epoch;
    logic [N_GATES-1:0] gate_response_seen;
    logic [N_GATES-1:0] clear_response_seen;
    logic gate_response_error;
    logic clear_response_error;
    wire all_participants_ready = safe_boundary
        && (&gate_cmd_ready) && (&clear_cmd_ready);
    wire [N_GATES-1:0] gate_response_accept = gate_rsp_valid & gate_rsp_ready;
    wire [N_GATES-1:0] clear_response_accept = clear_rsp_valid & clear_rsp_ready;
    wire [N_GATES-1:0] gate_response_seen_next =
        gate_response_seen | gate_response_accept;
    wire [N_GATES-1:0] clear_response_seen_next =
        clear_response_seen | clear_response_accept;

    assign commit_ready = (state == S_IDLE);
    assign rsp_valid = (state == S_RSP) || (state == S_HALT);
    assign rsp_status = response_status;
    assign rsp_id = active_commit_id;
    assign rsp_masks_flat = response_masks;
    assign gate_cmd_id = (state == S_IDLE) ? commit_id : active_commit_id;
    assign runtime_blocked = (state != S_IDLE);
    assign commit_epoch_state = commit_epoch;

    always_comb begin
        gate_cmd_valid = '0;
        gate_rsp_ready = '0;
        clear_cmd_valid = '0;
        clear_rsp_ready = '0;

        // 只有全体预检通过的同一拍才会向所有 gate 发出提交。
        if ((state == S_IDLE) && commit_valid && all_participants_ready)
            gate_cmd_valid = {N_GATES{1'b1}};

        if (state == S_WAIT_GATE)
            gate_rsp_ready = ~gate_response_seen;

        // 清历史同样要求全体 core 同拍接受，避免部分核心先清理。
        if ((state == S_ISSUE_CLEAR) && (&clear_cmd_ready))
            clear_cmd_valid = {N_GATES{1'b1}};

        if (state == S_WAIT_CLEAR)
            clear_rsp_ready = ~clear_response_seen;
    end

    integer response_index;
    always_comb begin
        gate_response_error = 1'b0;
        clear_response_error = 1'b0;
        for (response_index = 0; response_index < N_GATES;
                response_index = response_index + 1) begin
            if (gate_response_accept[response_index]
                    && (gate_rsp_status_flat[response_index*3 +: 3] != ST_OK))
                gate_response_error = 1'b1;
            if (clear_response_accept[response_index]
                    && (clear_rsp_status_flat[response_index*3 +: 3] != ST_OK))
                clear_response_error = 1'b1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            active_commit_id <= '0;
            response_status <= ST_OK;
            response_masks <= '0;
            commit_epoch <= '0;
            gate_response_seen <= '0;
            clear_response_seen <= '0;
            internal_error <= 1'b0;
        end else begin
            case (state)
                S_IDLE: begin
                    if (commit_valid && commit_ready) begin
                        active_commit_id <= commit_id;
                        response_masks <= '0;
                        if (!all_participants_ready) begin
                            response_status <= ST_UNSAFE;
                            state <= S_RSP;
                        end else begin
                            response_status <= ST_OK;
                            gate_response_seen <= '0;
                            state <= S_WAIT_GATE;
                        end
                    end
                end

                S_WAIT_GATE: begin
                    gate_response_seen <= gate_response_seen_next;
                    for (response_index = 0; response_index < N_GATES;
                            response_index = response_index + 1) begin
                        if (gate_response_accept[response_index])
                            response_masks[response_index*4 +: 4]
                                <= gate_rsp_masks_flat[response_index*4 +: 4];
                    end
                    if (gate_response_error) begin
                        response_status <= ST_INTERNAL;
                        internal_error <= 1'b1;
                        state <= S_HALT;
                    end else if (&gate_response_seen_next) begin
                        clear_response_seen <= '0;
                        state <= S_ISSUE_CLEAR;
                    end
                end

                S_ISSUE_CLEAR: begin
                    if (&clear_cmd_ready)
                        state <= S_WAIT_CLEAR;
                end

                S_WAIT_CLEAR: begin
                    clear_response_seen <= clear_response_seen_next;
                    if (clear_response_error) begin
                        response_status <= ST_INTERNAL;
                        internal_error <= 1'b1;
                        state <= S_HALT;
                    end else if (&clear_response_seen_next) begin
                        response_status <= ST_OK;
                        commit_epoch <= commit_epoch + 1'b1;
                        state <= S_RSP;
                    end
                end

                S_RSP: begin
                    if (rsp_ready)
                        state <= S_IDLE;
                end

                S_HALT: begin
                    internal_error <= 1'b1;
                end

                default: begin
                    response_status <= ST_INTERNAL;
                    internal_error <= 1'b1;
                    state <= S_HALT;
                end
            endcase
        end
    end

endmodule

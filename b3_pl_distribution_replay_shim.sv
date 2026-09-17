// CP5b 纯 PL 分布 replay：先捕获一组真实输入，再在 PL 内循环重放。
// 捕获阶段的 PS/DMA 只负责装载样本；正式计量从第一个 measure 样本开始，
// 不包含捕获、模型装载或逐样本 packet 协议开销。
`timescale 1ns/1ps
module b3_pl_distribution_replay_shim #(
    parameter integer INPUT_SAMPLES = 397,
    parameter integer WARMUP_SAMPLES = 1000,
    parameter integer MEASURE_SAMPLES = 10000,
    parameter integer CONTINUOUS_REPLAY = 0
) (
    input  logic        clk,
    input  logic        rst,

    input  logic [31:0] upstream_sample_data,
    input  logic [31:0] upstream_sample_id,
    input  logic        upstream_sample_valid,
    output logic        upstream_sample_ready,

    output logic [31:0] core_sample_data,
    output logic [31:0] core_sample_id,
    output logic        core_sample_valid,
    input  logic        core_sample_ready,

    input  logic [31:0] core_result_data,
    input  logic [31:0] core_result_sample_id,
    input  logic [31:0] core_result_mask_epoch,
    input  logic        core_result_valid,
    output logic        core_result_ready,

    output logic [31:0] downstream_result_data,
    output logic [31:0] downstream_result_sample_id,
    output logic [31:0] downstream_result_mask_epoch,
    output logic        downstream_result_valid,
    input  logic        downstream_result_ready,

    output logic [31:0] pl_replay_status,
    output logic [31:0] pl_replay_capture_count,
    output logic [31:0] pl_replay_completed_count,
    output logic [31:0] pl_replay_measured_cycles
);
    localparam integer INPUT_INDEX_WIDTH =
        (INPUT_SAMPLES <= 1) ? 1 : $clog2(INPUT_SAMPLES);
    localparam integer RUN_COUNT_WIDTH =
        (MEASURE_SAMPLES <= WARMUP_SAMPLES) ?
        ((WARMUP_SAMPLES <= 1) ? 1 : $clog2(WARMUP_SAMPLES + 1)) :
        ((MEASURE_SAMPLES <= 1) ? 1 : $clog2(MEASURE_SAMPLES + 1));

    localparam logic [2:0] STATE_CAPTURE = 3'd0;
    localparam logic [2:0] STATE_CAPTURE_WAIT_RESULT = 3'd1;
    localparam logic [2:0] STATE_REPLAY_PREFETCH = 3'd2;
    localparam logic [2:0] STATE_REPLAY_PREFETCH_WAIT = 3'd3;
    localparam logic [2:0] STATE_REPLAY_PREFETCH_READY = 3'd4;
    localparam logic [2:0] STATE_REPLAY_FEED = 3'd5;
    localparam logic [2:0] STATE_REPLAY_WAIT_RESULT = 3'd6;
    localparam logic [2:0] STATE_DONE = 3'd7;

    localparam logic [1:0] PHASE_WARMUP = 2'd1;
    localparam logic [1:0] PHASE_MEASURE = 2'd2;

    localparam logic [31:0] STATUS_CAPTURE = 32'd1;
    localparam logic [31:0] STATUS_WARMUP = 32'd2;
    localparam logic [31:0] STATUS_MEASURE = 32'd3;
    localparam logic [31:0] STATUS_PASS = 32'd4;
    localparam logic [31:0] STATUS_FAIL = 32'd5;

    logic [2:0] state;
    logic [1:0] phase;
    logic [INPUT_INDEX_WIDTH-1:0] capture_sample_index;
    logic [INPUT_INDEX_WIDTH-1:0] replay_sample_index;
    logic [3:0] capture_beat;
    logic [3:0] replay_beat;
    logic [3:0] result_beat;
    logic [RUN_COUNT_WIDTH-1:0] warmup_count;
    logic [RUN_COUNT_WIDTH-1:0] measured_count;
    logic [31:0] measured_cycle_counter;
    logic measuring;

    localparam integer SAMPLE_MEMORY_DEPTH = INPUT_SAMPLES * 8;
    localparam integer SAMPLE_ADDR_WIDTH =
        (SAMPLE_MEMORY_DEPTH <= 1) ? 1 : $clog2(SAMPLE_MEMORY_DEPTH);
    logic sample_mem_wr_en;
    logic [SAMPLE_ADDR_WIDTH-1:0] sample_mem_wr_addr;
    logic [SAMPLE_ADDR_WIDTH-1:0] sample_mem_rd_addr;
    logic [63:0] sample_mem_rd_data;

    assign sample_mem_wr_en = upstream_fire;
    assign sample_mem_wr_addr =
        (capture_sample_index * 8) + capture_beat;

    b3_distribution_sample_ram #(
        .DEPTH(SAMPLE_MEMORY_DEPTH),
        .ADDR_WIDTH(SAMPLE_ADDR_WIDTH)
    ) sample_ram (
        .clk(clk),
        .wr_en(sample_mem_wr_en),
        .wr_addr(sample_mem_wr_addr),
        .wr_data({upstream_sample_id, upstream_sample_data}),
        .rd_addr(sample_mem_rd_addr),
        .rd_data(sample_mem_rd_data)
    );

    wire upstream_fire = upstream_sample_valid && upstream_sample_ready;
    wire replay_fire = core_sample_valid && core_sample_ready;
    wire result_fire = core_result_valid && core_result_ready;
    wire forwarding_final_result =
        (CONTINUOUS_REPLAY == 0) &&
        (state == STATE_REPLAY_WAIT_RESULT) &&
        (phase == PHASE_MEASURE) &&
        (measured_count == MEASURE_SAMPLES - 1);

    always_comb begin
        upstream_sample_ready = 1'b0;
        core_sample_data = 32'd0;
        core_sample_id = 32'd0;
        core_sample_valid = 1'b0;
        core_result_ready = 1'b0;
        downstream_result_data = core_result_data;
        downstream_result_sample_id = core_result_sample_id;
        downstream_result_mask_epoch = core_result_mask_epoch;
        downstream_result_valid = 1'b0;

        case (state)
            STATE_CAPTURE: begin
                upstream_sample_ready = core_sample_ready;
                core_sample_data = upstream_sample_data;
                core_sample_id = upstream_sample_id;
                core_sample_valid = upstream_sample_valid;
            end
            STATE_REPLAY_FEED: begin
                core_sample_data = sample_mem_rd_data[31:0];
                core_sample_id = sample_mem_rd_data[63:32];
                core_sample_valid = 1'b1;
            end
            STATE_CAPTURE_WAIT_RESULT: begin
                core_result_ready = 1'b1;
            end
            STATE_REPLAY_WAIT_RESULT: begin
                core_result_ready = forwarding_final_result ? downstream_result_ready : 1'b1;
                downstream_result_valid = core_result_valid && forwarding_final_result;
            end
            default: begin
            end
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= STATE_CAPTURE;
            phase <= PHASE_WARMUP;
            capture_sample_index <= '0;
            replay_sample_index <= '0;
            capture_beat <= '0;
            replay_beat <= '0;
            result_beat <= '0;
            warmup_count <= '0;
            measured_count <= '0;
            measured_cycle_counter <= 32'd0;
            measuring <= 1'b0;
            pl_replay_status <= STATUS_CAPTURE;
            pl_replay_capture_count <= 32'd0;
            pl_replay_completed_count <= 32'd0;
            pl_replay_measured_cycles <= 32'd0;
            sample_mem_rd_addr <= '0;
        end else begin
            if (measuring)
                measured_cycle_counter <= measured_cycle_counter + 32'd1;

            if (state == STATE_CAPTURE && upstream_fire) begin
                if (capture_beat == 4'd7) begin
                    capture_beat <= '0;
                    result_beat <= '0;
                    state <= STATE_CAPTURE_WAIT_RESULT;
                end else begin
                    capture_beat <= capture_beat + 1'b1;
                end
            end

            if (state == STATE_CAPTURE_WAIT_RESULT && result_fire) begin
                if (result_beat == 4'd9) begin
                    result_beat <= '0;
                    pl_replay_capture_count <= pl_replay_capture_count + 32'd1;
                    if (capture_sample_index == INPUT_SAMPLES - 1) begin
                        replay_sample_index <= '0;
                        replay_beat <= '0;
                        sample_mem_rd_addr <= '0;
                        measured_count <= '0;
                        if (WARMUP_SAMPLES != 0) begin
                            phase <= PHASE_WARMUP;
                            pl_replay_status <= STATUS_WARMUP;
                        end else begin
                            phase <= PHASE_MEASURE;
                            pl_replay_status <= STATUS_MEASURE;
                        end
                        state <= STATE_REPLAY_PREFETCH;
                    end else begin
                        capture_sample_index <= capture_sample_index + 1'b1;
                        capture_beat <= '0;
                        state <= STATE_CAPTURE;
                    end
                end else begin
                    result_beat <= result_beat + 1'b1;
                end
            end

            if (state == STATE_REPLAY_PREFETCH) begin
                sample_mem_rd_addr <= replay_sample_index * 8;
                state <= STATE_REPLAY_PREFETCH_WAIT;
            end

            if (state == STATE_REPLAY_PREFETCH_WAIT) begin
                sample_mem_rd_addr <= (replay_sample_index * 8) + 1;
                state <= STATE_REPLAY_PREFETCH_READY;
            end

            if (state == STATE_REPLAY_PREFETCH_READY) begin
                sample_mem_rd_addr <= (replay_sample_index * 8) + 2;
                state <= STATE_REPLAY_FEED;
            end

            if (state == STATE_REPLAY_FEED && replay_fire) begin
                if (phase == PHASE_MEASURE && measured_count == 0 &&
                    replay_sample_index == 0 && replay_beat == 0) begin
                    measuring <= 1'b1;
                    measured_cycle_counter <= 32'd1;
                    pl_replay_status <= STATUS_MEASURE;
                end
                if (replay_beat == 4'd7) begin
                    replay_beat <= '0;
                    result_beat <= '0;
                    state <= STATE_REPLAY_WAIT_RESULT;
                end else begin
                    replay_beat <= replay_beat + 1'b1;
                    sample_mem_rd_addr <=
                        (replay_sample_index * 8) + replay_beat + 3;
                end
            end

            if (state == STATE_REPLAY_WAIT_RESULT && result_fire) begin
                if (result_beat == 4'd9) begin
                    result_beat <= '0;
                    if (phase == PHASE_WARMUP) begin
                        warmup_count <= warmup_count + 1'b1;
                        replay_sample_index <=
                            (replay_sample_index == INPUT_SAMPLES - 1) ?
                            '0 : replay_sample_index + 1'b1;
                        if ((warmup_count + 1'b1) >= WARMUP_SAMPLES) begin
                            phase <= PHASE_MEASURE;
                            measured_count <= '0;
                            replay_sample_index <= '0;
                            sample_mem_rd_addr <= '0;
                            pl_replay_status <= STATUS_MEASURE;
                        end
                        state <= STATE_REPLAY_PREFETCH;
                    end else if (phase == PHASE_MEASURE) begin
                        if (CONTINUOUS_REPLAY != 0) begin
                            pl_replay_completed_count <= pl_replay_completed_count + 32'd1;
                            replay_sample_index <=
                                (replay_sample_index == INPUT_SAMPLES - 1) ?
                                '0 : replay_sample_index + 1'b1;
                            sample_mem_rd_addr <=
                                ((replay_sample_index == INPUT_SAMPLES - 1) ?
                                 0 : (replay_sample_index + 1'b1) * 8);
                            state <= STATE_REPLAY_PREFETCH;
                        end else if ((measured_count + 1'b1) >= MEASURE_SAMPLES) begin
                            pl_replay_completed_count <= measured_count + 1'b1;
                            measuring <= 1'b0;
                            pl_replay_measured_cycles <= measured_cycle_counter + 32'd1;
                            pl_replay_status <= STATUS_PASS;
                            state <= STATE_DONE;
                        end else begin
                            pl_replay_completed_count <= measured_count + 1'b1;
                            measured_count <= measured_count + 1'b1;
                            replay_sample_index <=
                                (replay_sample_index == INPUT_SAMPLES - 1) ?
                                '0 : replay_sample_index + 1'b1;
                            sample_mem_rd_addr <=
                                ((replay_sample_index == INPUT_SAMPLES - 1) ?
                                 0 : (replay_sample_index + 1'b1) * 8);
                            state <= STATE_REPLAY_PREFETCH;
                        end
                    end else begin
                        pl_replay_status <= STATUS_FAIL;
                        state <= STATE_DONE;
                    end
                end else begin
                    result_beat <= result_beat + 1'b1;
                end
            end
        end
    end
endmodule

module b3_distribution_sample_ram #(
    parameter integer DEPTH = 3176,
    parameter integer ADDR_WIDTH = 12
) (
    input  logic                  clk,
    input  logic                  wr_en,
    input  logic [ADDR_WIDTH-1:0] wr_addr,
    input  logic [63:0]           wr_data,
    input  logic [ADDR_WIDTH-1:0] rd_addr,
    output logic [63:0]           rd_data
);
`ifdef SYNTHESIS
    xpm_memory_sdpram #(
        .ADDR_WIDTH_A(ADDR_WIDTH),
        .ADDR_WIDTH_B(ADDR_WIDTH),
        .AUTO_SLEEP_TIME(0),
        .BYTE_WRITE_WIDTH_A(64),
        .CLOCKING_MODE("common_clock"),
        .ECC_MODE("no_ecc"),
        .MEMORY_INIT_FILE("none"),
        .MEMORY_INIT_PARAM("0"),
        .MEMORY_OPTIMIZATION("true"),
        .MEMORY_PRIMITIVE("block"),
        .MEMORY_SIZE(DEPTH * 64),
        .MESSAGE_CONTROL(0),
        .READ_DATA_WIDTH_B(64),
        .READ_LATENCY_B(2),
        .READ_RESET_VALUE_B("0"),
        .RST_MODE_B("SYNC"),
        .SIM_ASSERT_CHK(0),
        .USE_EMBEDDED_CONSTRAINT(0),
        .USE_MEM_INIT(0),
        .WAKEUP_TIME("disable_sleep"),
        .WRITE_DATA_WIDTH_A(64),
        .WRITE_MODE_B("read_first")
    ) mem (
        .clka(clk), .ena(1'b1), .wea(wr_en), .addra(wr_addr), .dina(wr_data),
        .clkb(clk), .enb(1'b1), .addrb(rd_addr), .doutb(rd_data),
        .rstb(1'b0), .regceb(1'b1), .sleep(1'b0),
        .injectsbiterra(1'b0), .injectdbiterra(1'b0),
        .sbiterrb(), .dbiterrb()
    );
`else
    logic [63:0] mem [0:DEPTH-1];
    logic [63:0] rd_pipe;
    always_ff @(posedge clk) begin
        if (wr_en)
            mem[wr_addr] <= wr_data;
        rd_pipe <= mem[rd_addr];
        rd_data <= rd_pipe;
    end
`endif
endmodule

`timescale 1ns/1ps

module tb_b2_npu_status_probe;
    logic clk = 1'b0;
    logic resetn = 1'b0;
    logic [11:0] awaddr = '0;
    logic awvalid = 1'b0;
    wire awready;
    logic [31:0] wdata = '0;
    logic [3:0] wstrb = 4'hf;
    logic wvalid = 1'b0;
    wire wready;
    wire [1:0] bresp;
    wire bvalid;
    logic bready = 1'b1;
    logic [11:0] araddr = '0;
    logic arvalid = 1'b0;
    wire arready;
    wire [31:0] rdata;
    wire [1:0] rresp;
    wire rvalid;
    logic rready = 1'b1;

    logic [31:0] command_accept_count = 32'h11111111;
    logic [31:0] command_complete_count = 32'h22222222;
    logic [31:0] sample_accept_count = 32'h33333333;
    logic [31:0] sample_complete_count = 32'h44444444;
    logic [31:0] response_accept_count = 32'h55555555;
    logic [31:0] response_complete_count = 32'h66666666;
    logic [31:0] result_accept_count = 32'h77777777;
    logic [31:0] result_complete_count = 32'h88888888;
    logic [31:0] execute_group_count = 32'h99999999;
    logic [31:0] skip_group_count = 32'haaaaaaaa;
    logic [31:0] runtime_status = 32'hbbbbbbbb;
    logic [31:0] active_mask_epoch = 32'hcccccccc;
    logic [31:0] pending_mask_epoch = 32'hdddddddd;
    logic [31:0] last_compute_cycles = 32'heeeeeeee;
    logic [31:0] protocol_error_count = 32'habababab;
    logic fence_snapshot_valid = 1'b1;
    logic [255:0] fence_snapshot_counts = {
        32'hf7f7f7f7, 32'hf6f6f6f6, 32'hf5f5f5f5, 32'hf4f4f4f4,
        32'hf3f3f3f3, 32'hf2f2f2f2, 32'hf1f1f1f1, 32'hf0f0f0f0
    };

    always #5 clk = ~clk;

    b2_npu_status_probe dut (
        .s_axi_aclk(clk), .s_axi_aresetn(resetn),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .command_accept_count(command_accept_count),
        .command_complete_count(command_complete_count),
        .sample_accept_count(sample_accept_count),
        .sample_complete_count(sample_complete_count),
        .response_accept_count(response_accept_count),
        .response_complete_count(response_complete_count),
        .result_accept_count(result_accept_count),
        .result_complete_count(result_complete_count),
        .execute_group_count(execute_group_count),
        .skip_group_count(skip_group_count),
        .runtime_status(runtime_status),
        .active_mask_epoch(active_mask_epoch),
        .pending_mask_epoch(pending_mask_epoch),
        .last_compute_cycles(last_compute_cycles),
        .protocol_error_count(protocol_error_count),
        .fence_snapshot_valid(fence_snapshot_valid),
        .fence_snapshot_counts(fence_snapshot_counts)
    );

    task automatic check_read(input logic [11:0] address, input logic [31:0] expected);
        begin
            @(negedge clk);
            araddr = address;
            arvalid = 1'b1;
            do @(posedge clk); while (!arready);
            @(negedge clk);
            arvalid = 1'b0;
            do @(posedge clk); while (!rvalid);
            if (rresp !== 2'b00 || rdata !== expected)
                $fatal(1, "read mismatch addr=%03h expected=%08h actual=%08h resp=%b", address, expected, rdata, rresp);
        end
    endtask

    task automatic check_write(
        input logic [11:0] address,
        input logic [31:0] value,
        input logic [3:0] strobe,
        input logic [1:0] expected_resp
    );
        begin
            @(negedge clk);
            awaddr = address;
            awvalid = 1'b1;
            wdata = value;
            wstrb = strobe;
            wvalid = 1'b1;
            do @(posedge clk); while (!(awready && wready));
            @(negedge clk);
            awvalid = 1'b0;
            wvalid = 1'b0;
            do @(posedge clk); while (!bvalid);
            if (bresp !== expected_resp)
                $fatal(1, "write response mismatch addr=%03h expected=%b actual=%b",
                       address, expected_resp, bresp);
        end
    endtask

    task automatic check_write_split(
        input logic [11:0] address,
        input logic [31:0] value,
        input logic aw_first,
        input logic [1:0] expected_resp
    );
        begin
            @(negedge clk);
            if (aw_first) begin
                awaddr = address;
                awvalid = 1'b1;
                do @(posedge clk); while (!awready);
                @(negedge clk);
                awvalid = 1'b0;
                wdata = value;
                wstrb = 4'hf;
                wvalid = 1'b1;
                do @(posedge clk); while (!wready);
                @(negedge clk);
                wvalid = 1'b0;
            end else begin
                wdata = value;
                wstrb = 4'hf;
                wvalid = 1'b1;
                do @(posedge clk); while (!wready);
                @(negedge clk);
                wvalid = 1'b0;
                awaddr = address;
                awvalid = 1'b1;
                do @(posedge clk); while (!awready);
                @(negedge clk);
                awvalid = 1'b0;
            end
            do @(posedge clk); while (!bvalid);
            if (bresp !== expected_resp)
                $fatal(1, "split write response mismatch addr=%03h expected=%b actual=%b",
                       address, expected_resp, bresp);
        end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        resetn = 1'b1;
        check_read(12'h000, 32'h00000001);
        check_read(12'h004, 32'h11111111);
        check_read(12'h008, 32'h22222222);
        check_read(12'h00c, 32'h33333333);
        check_read(12'h010, 32'h44444444);
        check_read(12'h014, 32'h55555555);
        check_read(12'h018, 32'h66666666);
        check_read(12'h01c, 32'h77777777);
        check_read(12'h020, 32'h88888888);
        check_read(12'h048, 32'h99999999);
        check_read(12'h04c, 32'haaaaaaaa);
        check_read(12'h050, 32'hbbbbbbbb);
        check_read(12'h054, 32'hcccccccc);
        check_read(12'h058, 32'hdddddddd);
        check_read(12'h05c, 32'heeeeeeee);
        check_read(12'h060, 32'habababab);
        check_read(12'h024, 32'h00000001);
        check_read(12'h028, 32'hf0f0f0f0);
        check_read(12'h02c, 32'hf1f1f1f1);
        check_read(12'h030, 32'hf2f2f2f2);
        check_read(12'h034, 32'hf3f3f3f3);
        check_read(12'h038, 32'hf4f4f4f4);
        check_read(12'h03c, 32'hf5f5f5f5);
        check_read(12'h040, 32'hf6f6f6f6);
        check_read(12'h044, 32'hf7f7f7f7);
        check_read(12'h074, 32'h00000000);

        check_write(12'h074, 32'h43503849, 4'hf, 2'b00);
        check_read(12'h074, 32'h43503849);
        check_write_split(12'h074, 32'h43503853, 1'b1, 2'b00);
        check_read(12'h074, 32'h43503853);
        check_write_split(12'h074, 32'h43503852, 1'b0, 2'b00);
        check_read(12'h074, 32'h43503852);
        check_write(12'h074, 32'hdeadbeef, 4'h3, 2'b10);
        check_read(12'h074, 32'h43503852);
        check_write(12'h004, 32'hdeadbeef, 4'hf, 2'b10);
        check_read(12'h004, 32'h11111111);

        $display("B2_NPU_STATUS_PROBE_PASS");
        $finish;
    end
endmodule

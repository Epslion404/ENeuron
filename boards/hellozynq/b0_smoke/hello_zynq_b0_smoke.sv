module hello_zynq_b0_smoke (
    input  logic sys_clk_50m,
    output logic led
);
    logic [25:0] counter = '0;

    always_ff @(posedge sys_clk_50m) begin
        counter <= counter + 1'b1;
    end

    assign led = counter[25];
endmodule

// 三种已批准模型的固定二位证据增益适配器。
// 适配器只做组合饱和映射，不保存状态，也不包含剪枝排名逻辑。

module eneuron_prune_evidence_gain (
    input  logic [7:0] raw_evidence_flat,
    output logic [7:0] scaled_evidence_flat
);
    assign scaled_evidence_flat = raw_evidence_flat;
endmodule

module pulse_mini_l_prune_evidence_gain (
    input  logic [7:0] raw_evidence_flat,
    output logic [7:0] scaled_evidence_flat
);
    integer i;
    always_comb begin
        scaled_evidence_flat = '0;
        for (i = 0; i < 4; i = i + 1) begin
            case (raw_evidence_flat[i*2 +: 2])
                2'd0: scaled_evidence_flat[i*2 +: 2] = 2'd0;
                2'd1: scaled_evidence_flat[i*2 +: 2] = 2'd2;
                default: scaled_evidence_flat[i*2 +: 2] = 2'd3;
            endcase
        end
    end
endmodule

module pulse_mini_l2_prune_evidence_gain (
    input  logic [7:0] raw_evidence_flat,
    output logic [7:0] scaled_evidence_flat
);
    assign scaled_evidence_flat = raw_evidence_flat;
endmodule

// Host Bridge V1 可综合系统顶层：Host CDC 桥接、Tile 域控制器与 4->2->2 SNN Tile。
module digital_snn_host_bridge_system (
    input  logic         host_clk,
    input  logic         tile_clk,
    input  logic         bridge_rst,

    input  logic         host_cmd_valid,
    output logic         host_cmd_ready,
    input  logic [127:0] host_cmd_data,

    output logic         host_rsp_valid,
    input  logic         host_rsp_ready,
    output logic [127:0] host_rsp_data,
    output logic         status_irq,

    // 只读调试状态：用于双时钟仿真、CDC 检查和板级复位诊断。
    output logic         debug_host_rst,
    output logic         debug_tile_rst,
    output logic         debug_tile_domain_up,
    output logic [3:0]   debug_fifo_rst_busy,
    output logic         debug_tile_ready,
    output logic         debug_tile_busy,
    output logic         debug_tile_protocol_error,
    output logic [1:0]   debug_tile_output_spikes
);

    // Bridge Tile 域 FIFO 窄侧。
    logic         tile_cmd_valid;
    logic         tile_cmd_ready;
    logic [127:0] tile_cmd_data;
    logic         tile_rsp_valid;
    logic         tile_rsp_ready;
    logic [127:0] tile_rsp_data;

    logic host_rst;
    logic tile_rst;
    logic tile_domain_up;
    logic cmd_wr_rst_busy;
    logic cmd_rd_rst_busy;
    logic rsp_wr_rst_busy;
    logic rsp_rd_rst_busy;

    // Controller 到真实 Tile 的命令与状态通道，全部位于 tile_clk 域。
    logic         tile_state_clear;
    logic         tile_tick_valid;
    logic         tile_route_flush_valid;
    logic [3:0]   tile_input_spikes;
    logic         tile_learn_enable;
    logic         tile_snapshot_we;
    logic [15:0]  tile_snapshot_commit_id;
    logic [15:0]  tile_snapshot_episode_id;
    logic         tile_mod_valid;
    logic [15:0]  tile_mod_commit_id;
    logic signed [1:0] tile_hidden0_modulator;
    logic signed [1:0] tile_hidden1_modulator;
    logic signed [1:0] tile_output0_modulator;
    logic signed [1:0] tile_output1_modulator;
    logic         tile_weight_we;
    logic [1:0]   tile_neuron_addr;
    logic [1:0]   tile_weight_addr;
    logic signed [7:0] tile_weight_wdata;

    logic signed [7:0] tile_weight_rdata;
    logic         tile_ready;
    logic         tile_busy;
    logic         tile_done;
    logic         tile_protocol_error;
    logic [1:0]   tile_hidden_spikes;
    logic [1:0]   tile_output_spikes;
    logic [1:0]   tile_pending_hidden_state;
    logic         tile_snapshot_valid_state;
    logic [15:0]  tile_pending_commit_id_state;
    logic [15:0]  tile_pending_episode_id_state;
    logic         tile_last_commit_valid_state;
    logic [15:0]  tile_last_commit_id_state;
    logic [31:0]  tile_weight_epoch_state;

    // 跨时钟桥：Host 侧和 Tile 侧仅通过两个 128-bit 异步 FIFO 交换事务。
    digital_snn_host_bridge host_bridge (
        .host_clk(host_clk),
        .tile_clk(tile_clk),
        .bridge_rst(bridge_rst),
        .host_cmd_valid(host_cmd_valid),
        .host_cmd_ready(host_cmd_ready),
        .host_cmd_data(host_cmd_data),
        .host_rsp_valid(host_rsp_valid),
        .host_rsp_ready(host_rsp_ready),
        .host_rsp_data(host_rsp_data),
        .status_irq(status_irq),
        .tile_cmd_valid(tile_cmd_valid),
        .tile_cmd_ready(tile_cmd_ready),
        .tile_cmd_data(tile_cmd_data),
        .tile_rsp_valid(tile_rsp_valid),
        .tile_rsp_ready(tile_rsp_ready),
        .tile_rsp_data(tile_rsp_data),
        .host_rst(host_rst),
        .tile_rst(tile_rst),
        .tile_domain_up(tile_domain_up),
        .cmd_wr_rst_busy(cmd_wr_rst_busy),
        .cmd_rd_rst_busy(cmd_rd_rst_busy),
        .rsp_wr_rst_busy(rsp_wr_rst_busy),
        .rsp_rd_rst_busy(rsp_rd_rst_busy)
    );

    // Tile 域协议控制器：复位必须使用 Bridge 在 tile_clk 域同步后的 tile_rst。
    digital_snn_host_bridge_controller controller (
        .clk(tile_clk),
        .rst(tile_rst),
        .cmd_valid(tile_cmd_valid),
        .cmd_ready(tile_cmd_ready),
        .cmd_data(tile_cmd_data),
        .rsp_valid(tile_rsp_valid),
        .rsp_ready(tile_rsp_ready),
        .rsp_data(tile_rsp_data),
        .tile_state_clear(tile_state_clear),
        .tile_tick_valid(tile_tick_valid),
        .tile_route_flush_valid(tile_route_flush_valid),
        .tile_input_spikes(tile_input_spikes),
        .tile_learn_enable(tile_learn_enable),
        .tile_snapshot_we(tile_snapshot_we),
        .tile_snapshot_commit_id(tile_snapshot_commit_id),
        .tile_snapshot_episode_id(tile_snapshot_episode_id),
        .tile_mod_valid(tile_mod_valid),
        .tile_mod_commit_id(tile_mod_commit_id),
        .tile_hidden0_modulator(tile_hidden0_modulator),
        .tile_hidden1_modulator(tile_hidden1_modulator),
        .tile_output0_modulator(tile_output0_modulator),
        .tile_output1_modulator(tile_output1_modulator),
        .tile_weight_we(tile_weight_we),
        .tile_neuron_addr(tile_neuron_addr),
        .tile_weight_addr(tile_weight_addr),
        .tile_weight_wdata(tile_weight_wdata),
        .tile_weight_rdata(tile_weight_rdata),
        .tile_ready(tile_ready),
        .tile_done(tile_done),
        .tile_protocol_error(tile_protocol_error),
        .tile_hidden_spikes(tile_hidden_spikes),
        .tile_output_spikes(tile_output_spikes),
        .tile_snapshot_valid_state(tile_snapshot_valid_state),
        .tile_pending_commit_id_state(tile_pending_commit_id_state),
        .tile_pending_episode_id_state(tile_pending_episode_id_state),
        .tile_last_commit_valid_state(tile_last_commit_valid_state),
        .tile_last_commit_id_state(tile_last_commit_id_state),
        .tile_weight_epoch_state(tile_weight_epoch_state)
    );

    // 固定 4->2->2 Tile：Controller 的每个原语端口都连接到真实硬件状态机。
    digital_snn_tile_4x2x2 tile (
        .clk(tile_clk),
        .rst(tile_rst),
        .state_clear(tile_state_clear),
        .tick_valid(tile_tick_valid),
        .route_flush_valid(tile_route_flush_valid),
        .input_spikes(tile_input_spikes),
        .learn_enable(tile_learn_enable),
        .snapshot_we(tile_snapshot_we),
        .snapshot_commit_id(tile_snapshot_commit_id),
        .snapshot_episode_id(tile_snapshot_episode_id),
        .mod_valid(tile_mod_valid),
        .mod_commit_id(tile_mod_commit_id),
        .hidden0_modulator(tile_hidden0_modulator),
        .hidden1_modulator(tile_hidden1_modulator),
        .output0_modulator(tile_output0_modulator),
        .output1_modulator(tile_output1_modulator),
        .weight_we(tile_weight_we),
        .neuron_addr(tile_neuron_addr),
        .weight_addr(tile_weight_addr),
        .weight_wdata(tile_weight_wdata),
        .weight_rdata(tile_weight_rdata),
        .ready(tile_ready),
        .busy(tile_busy),
        .done(tile_done),
        .protocol_error(tile_protocol_error),
        .hidden_spikes(tile_hidden_spikes),
        .output_spikes(tile_output_spikes),
        .pending_hidden_state(tile_pending_hidden_state),
        .snapshot_valid_state(tile_snapshot_valid_state),
        .pending_commit_id_state(tile_pending_commit_id_state),
        .pending_episode_id_state(tile_pending_episode_id_state),
        .last_commit_valid_state(tile_last_commit_valid_state),
        .last_commit_id_state(tile_last_commit_id_state),
        .weight_epoch_state(tile_weight_epoch_state)
    );

    assign debug_host_rst = host_rst;
    assign debug_tile_rst = tile_rst;
    assign debug_tile_domain_up = tile_domain_up;
    assign debug_fifo_rst_busy = {
        rsp_rd_rst_busy,
        rsp_wr_rst_busy,
        cmd_rd_rst_busy,
        cmd_wr_rst_busy
    };
    assign debug_tile_ready = tile_ready;
    assign debug_tile_busy = tile_busy;
    assign debug_tile_protocol_error = tile_protocol_error;
    assign debug_tile_output_spikes = tile_output_spikes;

endmodule

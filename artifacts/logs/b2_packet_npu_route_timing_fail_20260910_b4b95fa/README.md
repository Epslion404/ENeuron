# B2 packet-NPU route/timing failure

- Date: 2026-09-10
- Source HEAD: `b4b95fa0e563ed99b14ffc4fcc80453e94806b1e`
- Vivado: 2024.1
- Part: `xc7z020clg484-2`
- Top: `design_1_wrapper`

`route_design` completed successfully and generated bitstream/XSA, but the 200 MHz `clk_fpga_0` setup gate failed:

- WNS: `-0.589 ns`
- TNS: `-45.751 ns`
- Setup failing endpoints: `363`
- WHS: `+0.019 ns`
- THS: `0`
- Route errors: `0`
- DRC hard errors: `0`

Worst reported path:

`b2_npu_axis_top/adapter/wrapper/core/mac_accumulator_reg[0]/C -> mac_accumulator_reg[28]/D`

The data path delay is `5.526 ns` (`2.961 ns` logic, `2.565 ns` route, 13 logic levels). The generated bitstream/XSA are retained only for failure analysis and must not be used for timing signoff or board programming.

This run includes the registered model-write staging change from `b4b95fa`; it is the latest complete build evidence for the current source line. The runner correctly raised `B2 timing gate failed` after report generation, so no passing manifest was produced by the build script. A failure-analysis manifest with report and artifact hashes is stored beside these files.

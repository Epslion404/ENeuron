# B2 packet-NPU route/timing failure

- Date: 2026-09-10
- Source HEAD: `8d57e7e232f543c76704f09c9640bb5aa8832834`
- Vivado: 2024.1
- Part: `xc7z020clg484-2`
- Top: `design_1_wrapper`

`route_design` completed successfully and generated bitstream/XSA, but the 200 MHz `clk_fpga_0` setup gate failed:

- WNS: `-1.958 ns`
- TNS: `-3308.760 ns`
- Setup failing endpoints: `5902`
- WHS: `+0.055 ns`
- THS: `0`
- Route errors: `0`
- DRC hard errors: `0`

Worst reported path:

`b2_npu_axis_top/adapter/wrapper/core/compute_unit_index_reg[0]_replica_1/C -> compute_group_index_reg[2]__0/CE`

The data path delay is `6.574 ns` (`1.497 ns` logic, `5.077 ns` route, 8 logic levels). The generated bitstream/XSA are retained only as failure-analysis artifacts and must not be used for timing signoff or board programming.

The build runner raised `B2 timing gate failed` after report generation. The archived `build_manifest.json` is a failure-analysis manifest generated from the same HEAD and report hashes; it is not a passing signoff manifest.

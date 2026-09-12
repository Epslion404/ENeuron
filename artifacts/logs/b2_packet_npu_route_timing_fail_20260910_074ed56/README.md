# B2 packet-NPU route timing failure: 074ed56

- Target: `xc7z020clg484-2`, top `design_1_wrapper`, NPU clock 200 MHz.
- Source commit: `074ed56886f4aad36bb9ce3149dbc54926e959d8`.
- Route completed with zero routing errors; DRC reported zero hard errors.
- Final setup timing failed: `WNS=-0.052 ns`, `TNS=-0.134 ns`, 6 failing endpoints.
- Hold timing passed: `WHS=+0.073 ns`, `THS=0`.
- Worst path: `compute_unit_mask_latched_reg[3]/C -> compute_group_index_reg[1]/D`.
- Data delay was `4.687 ns`, of which `3.272 ns` was routing delay.

The bitstream and XSA are retained for analysis only. They are marked
`analysis_only_no_download` and must not be programmed onto the board.

The Vivado host clock was one day ahead of the task date; the archive directory
uses the task date while the original timestamp remains in `vivado_run.log`.

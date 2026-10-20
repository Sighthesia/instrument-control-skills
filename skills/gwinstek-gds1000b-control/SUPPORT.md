# Parser Support Record

- Parser status: `documented`
- Hardware verification: `false`
- Verified model/firmware/interface: not yet verified
- Manual source: [*GDS-1000B Series Programming Manual*, Version 1.00, March 2015](https://www.gwinstek.com/en-global/products/detail/GDS-1000B) (local copy `ref/编程指令手册.pdf`)
- Supported data kinds: `identity`, `scalar-measurement`, `status-record` (error queue), and `waveform` (acquisition memory) from saved/offline data
- Known limitations: no transport verification; waveform voltage conversion is documented-only and uncalibrated; USB CDC serial defaults unstated (`115200 8N1` assumed); Ethernet on 4-channel models only, socket server off by default; no screenshot/file readback over SCPI; no calibration, firmware update, or automatic reset/save/recall

Do not upgrade this record to `hardware-verified` without preserving an actual
instrument response, `*IDN?` identity, model, firmware, interface, and test date.

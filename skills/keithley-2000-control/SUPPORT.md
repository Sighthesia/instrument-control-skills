# Support Record

- Support level: `documented`
- Hardware verification: `false`
- Verified model/firmware/interface: not yet verified
- Manual source: [Model 2000 Multimeter User's Manual, 2000-900-01 Rev. J / August 2010](https://download.tek.com/manual/2000-900_J-Aug2010_User.pdf)
- Supported data kind: one scalar ASCII reading or one error-queue line from a saved response
- Known limitations: no transport driver; no binary, multi-reading, or scanner parser; calibration, input-fuse continuity, and acquisition freshness are not inferred

Do not upgrade this record to `hardware-verified` without preserving an actual
instrument response, `*IDN?` identity, firmware, interface, and test date.

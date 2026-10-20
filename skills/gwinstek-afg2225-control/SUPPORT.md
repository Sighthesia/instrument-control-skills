# Parser Support Record

- Parser status: `documented`
- Hardware verification: `false`
- Verified model/firmware/interface: not yet verified
- Manual source: [AFG-2225 Series User Manual, GW Instek part no. 82RF-22250M01](https://www.gwinstek.com/en-global/products/detail/AFG-2225) (local copy `ref/编程手册.pdf`)
- Supported data kinds: identity, numeric, error-queue, and arbitrary-waveform command construction from saved/offline data
- Known limitations: no transport verification; binary ARB byte order unverified; USB CDC only; no calibration or non-volatile ARB save claim; manual example byte-count defect

Do not upgrade this record to `hardware-verified` without preserving an actual
instrument response, `*IDN?` identity, firmware, interface, and test date.
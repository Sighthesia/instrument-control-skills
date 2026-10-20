# Bench Setup and Panel Connectors (AFG-2225)

Manual: *AFG-2225 Series User Manual*, pp. 13-20, 181, 293. Support level:
`documented`.

## Outputs

- Front-panel `CH1` and `CH2` BNC outputs; both channels have the same
  25 MHz sine/square, 1 MHz ramp, 500 µHz-25 MHz pulse, and ARB capability
  (manual pp. 13-14, 293).
- Output impedance is 50 Ω typical (fixed); when output is disabled the
  connector presents >10 MΩ (manual p. 293).
- Use 50 Ω coaxial cable and a matching termination where the amplitude
  accuracy matters. `OUTPut:LOAD` is only a **reference** setting: if it says
  50 Ω but the actual load is different, amplitude and offset will be wrong
  (manual p. 213).
- Do not exceed the amplitude/offset limits in
  [basic-waveforms.md](basic-waveforms.md). The output is short-circuit
  protected, but an external overload turns the output off until the overload
  is removed (manual p. 213).

## Rear panel

| Connector | Purpose | Manual page |
|---|---|---|
| USB device (Type-B) | Remote control virtual COM port | 181 |
| USB host (Type-A) | USB flash drive, firmware update, waveform transfer | 16-17 |
| Trigger INPUT | External burst/sweep trigger or gate | 16-17, 249 |
| Trigger OUT | Marker/SYNC or burst trigger output | 16-17, 247-248, 257 |
| MOD INPUT | External AM/FM/PM/SUM modulation, ±5 V | 16-17, 219 |
| Counter input | Frequency-counter input | 16-17, 266 |
| AC power | 100-240 V, 50-60 Hz, 25 W maximum | 16-17, 293 |

## Power-up and environment

- Specifications apply after at least 30 minutes warm-up at 18-28 °C
  (manual p. 293).
- Operating: 0-40 °C, relative humidity <80 %, altitude <2000 m, pollution
  degree 2, installation category CAT II (manual pp. 7-9, 293).
- Do not open the case or replace the fuse unless qualified; disconnect power
  and leads first (manual pp. 7-9).

## Remote-mode panel behavior

When a remote connection is established, panel keys are locked except F5
(REM/LOCK); press F5 to return to local control (manual p. 182).

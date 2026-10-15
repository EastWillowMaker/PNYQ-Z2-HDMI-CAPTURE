# Build016 CAD passed; physical source was inactive

The isolated build finished with exit0 at 2026-10-15 08:43:57 Asia/Taipei.
It uses the equivalent equality watchdog RTL and S2MM free-run mode. HLS was
reused from the successful fresh HLS stages of015; the failed015 top routing
was not reused. Inputs remain frozen under `artifacts/m1-project-016-source`.

- Setup/hold0.399/0.033ns; no no-clock or unconstrained internal endpoints.
- All56 bus-skew constraints MET; main/child logs contain no ERROR/CRITICAL.
- CDC161 synchronized-bit info, four reset info, one retained VTC warning.
- Routed readback retains all256 Gray and six reset/data ASYNC_REG registers.
- Paired bit SHA `a8c661dc9c3478471a34a23d697a33f0a428308b0ad5b482181187f646574578`.
- HWH SHA `24a32f91ce95594ed1573f9024174aab39505c7ed153d605acbd4c78e77746b0`.
- Manifest declares free-run, held identity and next-SOF completion policy;
  HWH verifies S2MM per-channel Fsync0 and enabled frame-counter/debug15.

Retained DRC/methodology warnings, five input/two output delay gaps and vendor
XPM waivers remain; this is not a warning-free or full external-I/O qualification.
The strict original timing/CDC/DRC gates were retained. Source/paired hashes
were independently read back before packaging. Local64 gate/manifest and135
producer/qualifier checks pass; no hosted CI result is claimed.

V9 source archive SHA
`12a7fce8bb79aa796b433b7afafdcf65e00a79fd9c082d1ea6e99381e7c3e06a`;
overlay016 archive SHA
`2fded63c6f20e517e30b74a386b9196e4fee73c7e1ba544fa2a4982e9c475adc`.
Both board transfer hashes match. Actual PYNQ import, paired artifact validation,
overlay load and native frontend construction reached source configuration.
No running-signal or DMA auto-halt correctness is established yet.

The first source configuration failed with `No incoming video signal detected`.
Host observation at that time showed ScreenSaver.GetActive=true, DisplayConfig
PowerSaveMode=3, and DRM DP-2 connected but inactive with DPMS3/no encoder.
The GLES framebuffer self-checks still passed, demonstrating why they alone do
not prove active HDMI scanout. **Zero physical frames were acquired/delivered.**
The sender exited before native buffer allocation/DMA start; board remains alive.
Known UIO destructor warning is retained in `m1-016-v9-no-signal.log`.

The bounded shader and scanout processes both exited normally with status0.
Shader log SHA
`47778685aff18d47c0693bea0ac563d01c9c6b5bef682d1ac0cff312c047b2c5`.
Raw scanout/events remain local in `artifacts/operator/m1-016-smoke-*`.
The operator was asked to wake/unlock the PC desktop and leave HDMI connected.
The screen lock has not been altered by software. Before restart, verify active
DRM output and display power, then keep the existing SDL idle inhibitor alive
through the capture window. Full M1 remains incomplete.

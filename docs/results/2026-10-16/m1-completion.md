The accepted fixed-mode M1 is complete: PC Python received real PYNQ-Z2 HDMI IN
as complete raw RGB888 arrays through LiteX capture, parked VDMA/PS DDR and PS
Ethernet. Normal019 delivered1,201 distinct exact640×480 frames in600.300346s
at2.000665FPS. Pixel, mixed/repeated-frame, metadata and transport errors were0.
Normal sender cleanup, independent DMA halt, storage and source/desktop return
passed. The [aggregate record](m1-completion.json) identifies scope and hashes;
individual historical or single-purpose results retain their original flags.

| Obligation | Verified evidence |
| --- | --- |
| ≥600s, ≥600newframes, ≥1FPS on real LiteX HDMI | [Normal019](m1-017-normal-019.md):1,201exact/600.300346s/2.000665FPS; all optical IDs match actual KMS presentations |
| Owned complete buffer, safe release and accounting | [Lease015](m1-017-lease-015-report.md): held DDR/RGB/identity stable through119native edges, ACK then a newer capture;019 received-window36,001native intervals =1,200acquisitions+34,801intentional skips |
| Clean-source public first-frame workflow | [Clean023](m1-017-clean-023.md): complete isolated ad6c966 export, public wait→prepare→sender/trigger/client,41exact20.309945s; endpoint arrays `(480,640,3)` uint8 RGB |
| Physical HDMI IN unplug/reconnect with live client | [Confirmed024](m1-017-hdmi-loss-024.md): user HDMI-only5s action,101exact then boundaryEOF, explicit source error, safe halt/free, no SIGBUS/new abort/storage error |
| Explicit recovery after that physical loss | [Restart025](m1-017-restart-025.md):21exact10.109394s under a new session, zero normal source/cleanup/network errors, actual exit0 and safe halt/storage/source/VT return |
| Supported input timing transition | [Mode021](m1-017-mode-021.md):25200→25175kHz nominal640×480 timing,47exact before EOF during modeset, rejected invalid input and safe stop;023 subsequently restarted |
| Client pause/reconnect | [010](reconnect-010-report.md) plus current015/019 ownership/drop evidence; networking/lifecycle methods remain unchanged through3343dac, as the [bounded audit](m1-final-evidence-audit.md) records |
| Rebuild and tests | [Clean017 replay](credit-017-clean-replay.md): fresh HLS/RTL/CAD606.745s, setup/hold0.401/0.014ns,56skewchecks met, no criticalCDC/DRC; [host checks](sender-readiness-wait.md):490passed/1optional skip, focused60passed |

The acquisition runtime is3343dac; the isolated source export isad6c966, which
adds the host90s readiness observation and fatal-log guard. Acquisition and DMA
teardown were unchanged by that host correction. The exact clean-replay017
bit/HWH/manifest pair was used in the current hardware runs. Existing tested
Python/XRT dependencies were reused for the clean-source replay. This does not
claim another fresh dependency installation, hosted CI run or new CAD build.
The practical path is [quickstart](../../quickstart.md) followed by
[prepared capture](../../prepared-capture.md); use `--source litex-credit`.
The input must be stable before native frontend startup. A source fault ends the
session; normal preparation and explicit restart are the supported policy.

Earlier failures remain: the SD/SIGBUS history, physical012, observer020,
mode021's acknowledgment race, clean023's kernel-count false failure and the
025 host-only prerequisite rejection. Corrected or independent evidence is
separate and hash-linked. Historical flags were not rewritten. Physical024's
one cleanup counter is the predeclared exact final-source-proof rethrow after
verified safe release; it is retained as a fault, not silently erased or treated
as a general cleanup waiver. Normal captures still require zero such errors.

Limits remain explicit. This qualifies unencrypted eight-bit RGB640×480
progressive near60Hz, one TCP client and the tested PYNQ/PC path. The source
advertises no other geometry; unsupported-geometry hardware stimulus is NOT_RUN.
Nominal DRM timing is not a physical clock measurement. Source format/range
metadata remains unknown, native startup skips remain unknown, and absolute
optical-ID/native-edge association remains independently unverified. The receipt
is a software configuration ledger, not a hardware identity or unique epoch.
Native VTC startup still requires the pixel clock. The post-safe-cleanup PYNQ
UIO destructor warning and documented timing/CDC/external-I/O limits remain.
None of these observations extends support to arbitrary HDMI modes or guarantees
safe forced termination of an active native/DMA process.

Final read-only checks found no board capture sender, ext4 errors0 and an
unchanged boot. The root024→025 chain passed; the bounded PC source worker ended
normally after source exit and desktop restoration. Web, active bypass and LCD C
remain later milestones. No push, PR, external image upload or global package
installation was performed for this delivery.

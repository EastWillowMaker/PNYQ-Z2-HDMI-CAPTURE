HDMI-loss020 did not complete its planned capture observation. The user
confirmed unplugging and reconnecting only the PYNQ HDMI IN cable for about
five seconds, with the USB-C Hub and Micro-B untouched. The original
[controller](m1-017-hdmi-loss-020-controller.json) remains failed.

The host observer waited 45 seconds for production preparation plus native
sender startup. It timed out before the sender logged its actual listening
event, so no TCP client was started and no image was received. The sender
subsequently acquired 60 frames without a consumer. The source logged a page
flip error and exited1; VT restoration passed. This is not a pixel pass or a
completed physical-loss qualification.

The [root result](m1-017-hdmi-loss-020-result.json) records sender exit1,
source_errors1 and source_cleanup_errors1. It also records safe DMA shutdown,
VDMA CR0x15010/SR0x11001, gate command0, unchanged boot, ext4 errors0 and the
unchanged 16 MiB storage hash. The before/after kernel logs contain no new
external abort. There was no SIGBUS. The old source worker finished normally
after its current source had exited and a stop file was set; no process signal
or emergency DMA recovery was used.

The cleanup counter needs its exact scope. `Sender.close` increments it for
any exception from `source.close`. This traceback ends at the final rethrow in
`LiteXCreditSource.close`: the fixed-clock final source-accounting proof found
the persistent sequence fault. The code then disabled the gate, halted DMA,
stopped the frontend, freed the buffer and set `dma_shutdown_safe=True` before
raising that saved proof error. Independent raw readback supports successful
hardware teardown. This differs from an unknown halt, failed free, or native
signal fault; it does not justify treating arbitrary cleanup errors as safe.
Existing source and sender tests explicitly expect this final-proof behavior.
No production source behavior was changed for this classification. The inherited
ignored PYNQ UIO destructor warning is retained separately in the log.

The [separate analysis](m1-017-hdmi-loss-020-analysis.json) records the human
confirmation, evidence hashes and reviewed source hash, without rewriting the
original verdict. A repeat needs a client connected before the manual event,
a bounded readiness observation that covers actual startup, preserved source
fault reporting, safe halt, and an explicit supported-source restart. Normal
capture must still have zero source, cleanup, pixel and metadata failures.
Full M1 remains incomplete.

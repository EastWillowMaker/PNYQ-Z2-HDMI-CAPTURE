# Build014 first board execution

The v6 and overlay archives were transferred to a new `/tmp/hdmi-capture-credit`
directory and their SHA256 values matched the deployment checkpoint. After local
sudo renewal, the real 640x480p59.94 source fixture started and build014 loaded.

The gate selected one source frame, reached next-SOF-closed DONE, and held
accepted-SOF65/native-VSYNC66 identity with selected_completed1. No new invalid,
FIFO overflow/underflow or source-sequence fault occurred. The VDMA observed
running, but raw status remained0x10000 and control0x15011: no frame IRQ, no
automatic halt. Acquisition timed out; **zero frames were delivered**. This
attempt fails the capture contract and is retained in `m1-014-v6-smoke-full.log`.

Cleanup explicitly changed control0x15011→0x15010 and status0x10000→0x10001 before
freeing the buffer. `dma_shutdown_safe=true`; process exited, board remained alive.
Final 50ms source-accounting interval saw three native edges and no sticky faults.
The known UIO destructor warning remains. No forced kill or SD modification.

## Qualifier integration correction

A real producer→sender metadata→TCP encode/decode→qualifier regression initially
failed despite exact RGB pixels: the qualifier still required the legacy
`litex_video_gate` name and old after-DMA-start baseline point. Formal mode now
requires `litex_single_credit_gate` and the actual disabled/halted baseline
`before_first_credit_while_gate_disabled_dma_halted`; explicit legacy mode retains
the old names. The next-SOF closure policy is now also required. Seventy focused
qualification tests pass, including three actual producer samples over a socket
pair with native sequence gaps reconciled to58 intentional skips. These are
fake-MMIO/software integration results, not physical source qualification.

## DMA investigation

Build014 HWH has C_USE_S2MM_FSYNC=2 (TUSER) and C_USE_FSYNC=1. Vendor register
logic reloads the interrupt counter when the first synchronization is not yet a
valid frame synchronization; this provides a plausible explanation for a single
selected frame not producing the count/halt event. The root cause requires
stronger IP/physical evidence; it is not yet a completed-frame claim.

The official [PG020 control register](https://docs.amd.com/r/en-US/pg020_axi_vdma/S2MM_VDMACR-S2MM-VDMA-Control-Register-Offset-30h)
specifies automatic halt only after complete configured transfers. Its
[Fsync options](https://docs.amd.com/r/en-US/pg020_axi_vdma/Fsync-Options)
describe free-run mode as transferring without an external frame trigger.
A new isolated candidate will use that supported mode with the unchanged
single-credit frame gate. Manual stop or IRQ alone will not be accepted as
successful DMA completion. No new candidate is qualified yet.

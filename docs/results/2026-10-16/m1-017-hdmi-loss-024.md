Physical HDMI-loss024 passed its confirmed interruption/fail-stop scope. The
user confirmed unplugging only the PYNQ HDMI IN cable for about5seconds and
reconnecting it, with the USB-C Hub and Micro-B unchanged. The separate
[verified result](m1-017-hdmi-loss-024-verified.json) links the unchanged
observer/root/client/source evidence. The original controller retains
`passed:false` because it deliberately awaits a separate human confirmation.

The PC received101distinct exact640×480 RGB888 frames before interruption.
Every decoded optical ID occurs in the new KMS presentations. Pixel and metadata
checks passed; the received stream had no partial-frame EOF. At102.938447s
from the first KMS generation, the client received `EOF after 0 of 20 bytes`,
which is the boundary before a new frame prefix. It did not accept a partial
prefix, metadata or payload as a good image. The bounded checker records this
EOF text match because the existing SDK exposes no read-stage field; the real
fixture metadata and921600-byte payload are larger than20bytes.

This run declared its fault criteria before execution. The sender had to report
an input error and stop safely, rather than meet normal zero-source-error
criteria during the intentional negative stimulus. Its actual exit was1.
One source error and one final source-accounting error were retained. The latter
is counted by the existing broad cleanup counter, but only the exact known
final-proof case qualifies: pinned source hash/path, matching sequence-fault
messages, traceback at final accounting and the final rethrow after native
buffer release, plus independent safe raw readback. Arbitrary cleanup errors,
SIGBUS, unknown halt, changed storage or partial transport input reject the test.

The [root result](m1-017-hdmi-loss-024-result.json) confirms that exact case,
DMA shutdown safe, CR0x15010/SR0x11001 and command2 with gate disabled. The
sender stopped and released resources; no emergency reset, overlay recovery or
native process signal was used. Boot stayed unchanged. Ext4 errors stayed0 and
the16MiB storage file retained its known hash. The kernel logs have continuous
overlap and no new external abort. There was no SIGBUS. Source overrun
attribution after the integrity fault remains unknown, rather than fabricated0.

The240s direct-KMS source continued after the short interruption, exited0 and
restored the desktop. Receiver and client readiness were recorded before the
scheduled100s manual event; three exact frames arrived by53.483s. The observer
started no TCP probe and made no failed-test retry. Source diagnostics, invalid
input and all received frame verification records remain in the evidence.

This proves safe physical interruption with a live client on the unchanged
3343dac acquisition runtime and verified017 pair. It does not implement
automatic recovery. Explicit production restart025 is a separate check. The
failed012 SIGBUS and incomplete020 observation are preserved in their dated
reports; this result does not rewrite those historical outcomes.

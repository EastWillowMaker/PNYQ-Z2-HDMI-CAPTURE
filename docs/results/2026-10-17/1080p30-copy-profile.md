# Board CPU measurements before real HDMI qualification

These CPU-only measurements used the board's existing Python/NumPy environment
and the staged `df5410d` runtime. They did not import PYNQ, configure an overlay,
allocate DMA buffers or use the network. They measure ordinary cached arrays;
the cost of reading a native DMA allocation remains unmeasured.

Five iterations of generation, BGR-to-RGB copying and protocol encoding gave:

| Operation | Median time |
| --- | ---: |
| Generate synthetic 1920×1080 RGB888 | 68.452 ms |
| Reverse channel stride and copy | 266.839 ms |
| Encode one RGB888 frame | 121.460 ms |

The process used 4.207917 CPU seconds over 4.208624 wall seconds and reached
65,328 KiB maximum RSS. The complete test includes input preparation and exact
pixel assertions outside the individually timed operations. These phase times
must not be treated as a measured capture pipeline FPS. The script and raw log
are `artifacts/deploy/1080p30-001/copy-profile-002.py` and
`artifacts/operator/1080p-copy-profile-002.log`.

A second test reused one full 6,220,800-byte image for five copies per method.
The reversed-stride copy had a 269.953 ms median. Allocating a new array and
assigning the three channels separately had a 100.198 ms median, a 2.69× speedup
for this operation. Both methods produced independent arrays with every RGB
byte equal to the expected image. Its SHA256 was
`e9a97285ca7269a88a2fecacef59d5c394ac1334f3cac2b582b95edbd797caec`.
Maximum RSS was 66,364 KiB. The script and raw log are
`artifacts/deploy/1080p30-001/copy-compare-002.py` and
`artifacts/operator/1080p-copy-compare-003.log`.

The initial phase script rejected incomplete protocol metadata; its original
failure is retained in `1080p-copy-profile-001.log`. An optional OpenCV probe
did not complete within observation time and was interrupted only after
confirming it was our CPU-only process with no DMA. No OpenCV performance
result or dependency change is claimed. The NumPy-only comparison returned
normally. A later transfer attempt failed because the temporary HTTP server
had ended; the successful comparison was transferred through UART instead.

Commit `0acd289` applies the channel-copy change to `Sample.copy_rgb` using
plain ndarray allocation. A board measurement called the production method
directly and compared it with the previous implementation on the same ordinary
BGR array. It alternated method order for five rounds. The previous median was
267.649 ms; production was 99.748 ms, a 2.68× speedup. Every RGB byte matched;
each result was an independent, C-contiguous, read-only plain ndarray. The
assertions were outside the timed method calls. They dominate the total
22.845-second experiment; that duration is not a copy throughput result.

See the [production result](1080p30-production-copy-001.json). The raw log and
harness are `artifacts/operator/1080p-production-copy-001.log` and
`artifacts/operator/profile-sample-copy.py`. The source-file SHA256 was
`04bad9a7a1ad56bf3bd483d022dec76e09e08adff23ea20311d2505c2ad015d7`.
The verified source archive, including the profile-aware held-lease checker,
is deployed at `/tmp/hdmi-capture-1080p30-002`; archive SHA256 is
`23b86f94231cc66c41d42db3042d3c141f60ed31ea51f0e3013a4d473c06fb2a`.

The host suite passed 574 tests with one optional Migen/LiteX module skipped.
The added full1080p tests cover both RGB and BGR strided ndarray subclasses,
pixel equality, independent ownership and release timing. No performance
threshold is imposed in tests. The sender still copies while holding the lease
and closes the sample in its existing `finally` path. No DMA or ACK behavior
changed. Native-buffer copy cost and real HDMI throughput remain pending.

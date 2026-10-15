# Written image could not be read by the original verifier

## Observed failure

The guarded new-card writer completed 7,858,807,808bytes and fsync/cache flush.
Its readback subprocess returned exit 1 with zero bytes and`Invalid input`.
The empty-stream SHA256 is not a card-content hash. The old error text
`Full image readback does not match` incorrectly conflated inability to read
with a completed comparison that differs. Original evidence is retained in
[new-card-first-readback.json](new-card-first-readback.json) and its.log.
No rewrite is required merely because this verifier failed.

The detected `/usr/bin/dd` resolves to `/usr/lib/cargo/bin/coreutils/dd`,
uutils 0.8.0. The same direct/count_bytes invocation also fails in milliseconds
on the already verified local image, readingzero bytes, with`Input/output error`.
This establishes a reproducible verification-tool failure independent of the
SD device. It does not by itself prove that the new card is correct.

## Ranked predictions and controlled test

1. The dd direct-I/O path is incompatible: an explicitly aligned reader succeeds
   on the same local image where dd fails.
2. The card interface rejects the mode: the aligned local read succeeds but the
   raw card read fails. This needs actual privileged device execution.
3. Actual media/content fault: a reliable reader reports I/O errors or completes
   all bytes with a different SHA. A zero-byte verifier failure cannot decide it.

The first actual local 4 MiB red/green comparison is in
[sd-readback-local-reproduction.json](sd-readback-local-reproduction.json).
The new reader uses posix_memalign(4096), opens O_RDONLY|O_DIRECT, and preads bounded
512-aligned transfers into that buffer. It closes/free resources on error,
rejects incomplete transfers, and hashes only the requested full input.
It successfully read the whole local 7,858,807,808-byte image and matched its
known SHA256, recorded in[sd-readback-local-full.json](sd-readback-local-full.json).
The precise internal uutils defect is unverified; do not assert an upstream
implementation fix or general incompatibility across all versions/devices.

The maintained reader is `tools/aligned_readback.py`; the one-run operator copy
is byte-identical under`artifacts/operator/aligned-readback.py`. Seven execution
tests use actual direct-I/O on regular files in this repository filesystem,
including 512/4096/8 MiB+512-byte exact hashes, a short-file rejection, and invalid
length rejection. All 7 pass locally; these are not raw-card hardware tests.
No hosted CI was run.

## Recovery action and acceptance impact

Prepared command, verification only, no media writes:

```sh
sudo /usr/bin/python3 artifacts/operator/verify-new-pynq-sd.py
```

It guards the already-written new-card CID/capacity and requires unmounted,
kernel-read-only state. It records a separate result in`new-card-verify-001/`,
preserving the first failure. The raw read must finish all image bytes with
SHA256`f17405d25298a2c5ea23ccf95f868b42b18f819ff9d7fe5d079ac9ef53415861`
before reportingverified=true. The subsequent new-card execution passed. Its result is recorded below.

The original raw device/identity guard and image hash remain mandatory.
Supported512-byte-aligned complete inputs now use explicit aligned direct reads;
invalid lengths, inaccessible paths, unsupported direct I/O, short reads and
read errors fail. No buffered fallback masks an unsupported configuration.
A completed hash mismatch is recorded separately from inability to complete a
read. Other filesystems, devices, sector sizes and operating systems are
unverified. There is no write path in the reader or verification-only helper.
The one-run writer was updated to use the same reader for any future separately
authorized write; it was not rerun on this card.

## Completed new-card verification

The verification-only helper read all 7,858,807,808 bytes from the identified
new SD card in 94.805 seconds. It used the aligned O_DIRECT reader and wrote
zero bytes to the card. The complete read matched SHA256
`f17405d25298a2c5ea23ccf95f868b42b18f819ff9d7fe5d079ac9ef53415861`.
No error occurred. See [new-card-readback-verified.json](new-card-readback-verified.json).

This confirms the written image matches the downloaded official image. The
first zero-byte result was a verifier failure, not a completed comparison that
found different content. No second flash was needed. Card boot, long-term
reliability and unused capacity beyond the image remain unverified. PYNQ
first-boot and storage checks are the next step before loading the overlay.

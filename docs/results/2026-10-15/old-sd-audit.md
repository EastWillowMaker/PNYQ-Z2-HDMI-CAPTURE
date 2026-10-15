# Old PYNQ SD card: read-only host audit

Date: 2026-10-15 (Asia/Taipei)

## Device identity and current state

The old PYNQ card enumerated as `/dev/sdb`, USB SCSI target `0:0:0:1`, behind
`Generic MassStorageClass` reader serial `000000002958` (USB VID:PID `05e3:0764`).
The kernel reports 31,207,424 logical sectors of 512 bytes (16.0 GB / 14.9 GiB).
It exposes a 130 MiB FAT16 `PYNQ` partition (`/dev/sdb1`, UUID `8498-161A`)
and a 14.8 GiB ext4 `root` partition (`/dev/sdb2`, UUID
`40aa3f0d-35f3-47ee-96d1-9fb50b1adbbd`). The reader reports write-protect off,
write cache disabled and read cache enabled. The block device reports 512-byte
logical and physical sectors.

At the start of this audit, `/dev/sdb1` was still mounted read-write according
to the task handoff. During collection, the parent unmounted it with
`udisksctl`; `/dev/sdb2` remained unmounted. A subsequent `findmnt` showed
neither old-card partition mounted. This report records that observed state; it
does not perform mount or unmount operations. The initial system-wide `lsblk`
inventory incidentally displayed `mmcblk0` metadata; no block or filesystem
operation was directed at the new card and no writes were made to it.

## Evidence collected

Read-only host metadata commands:

- `lsblk -o NAME,MAJ:MIN,SIZE,RO,TYPE,FSTYPE,FSVER,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL,TRAN /dev/sdb`
- `udevadm info --query=all --name=/dev/sdb`
- sysfs reads of `/sys/class/block/sdb/{ro,size,device/{vendor,model,rev,state},queue/{logical_block_size,physical_block_size}}`
- `journalctl -k -b --no-pager`, filtered to `sdb`, partition names, and block/filesystem I/O errors

The current host kernel journal records insertion at 2026-10-15 22:03:50 local,
recognizes the two partitions, and at 22:03:52 reports:

> FAT-fs (sdb1): Volume was not properly unmounted. Some data may be corrupt. Please run fsck.

The captured current-boot journal has no `sdb` medium error, `I/O error`, or
`Buffer I/O error` line. This only describes the host session so far; it is not
evidence that all card sectors are readable. At the initial metadata-audit
snapshot, no card-content read or filesystem check had been performed; the
later partial preservation pass is described below.

The first `dmesg --ctime` attempt failed with `Operation not permitted`.
`journalctl -k` was readable and supplied the insertion evidence above. No
SMART or other media-health telemetry was obtained; the USB bridge identifies
itself only as generic mass storage.

The coordinator reports that unprivileged raw reads of `/dev/sdb` are denied
and `sudo -n` requires interactive authentication. `ddrescue` was not
installed at the time of the initial metadata audit; a local extracted package
was prepared for the controlled image pass. I did not request interactive sudo
or perform any raw read.

## Assessment

The FAT warning establishes an unclean prior removal and possible FAT
inconsistency. By itself, it does not establish physical media failure or
explain the observed ext4 errors.

The prior capture report, [m1-017-kms-001-report.md](m1-017-kms-001-report.md),
records `/usr/bin/sudo`, `ps`, and `tail` failing with I/O errors while the
PYNQ board reported ext4 directory-read errors on `mmcblk0p2`; the sender also
recorded a fatal `SIGBUS`. That is stronger evidence of a serious read-path
failure than the host's FAT warning, but it does not distinguish damaged
filesystem metadata from an SD/media, reader, or board MMC read-path problem.
The complete host-side image pass below is positive evidence that this reader
and host read the whole card once without ddrescue-reported read errors. It does
not establish physical health or rule out intermittent faults, and does not
explain the earlier board-side I/O errors. The card's physical health remains
unknown.

I performed no filesystem repair, `fsck`, `e2fsck`, `fstrim`, mount, raw scan,
or content read. The coordinator performed the preservation pass and
read-only filesystem checks described below. No repair was performed.

## Preservation pass progress snapshots

The coordinator reports the pass began at 2026-10-15 22:17:12 local. At the
22:22:45 mapfile update, the saved map covered a `+` range from byte 0 through
`0x1DD010000`, followed by a `?` range; it listed no bad-sector range. The
mapfile snapshot therefore lagged the live console output.

The ddrescue console log, last modified 22:23:02 local, shows 8,034 MB
rescued (50.28%) after 5m50s, zero read errors, zero bad sectors, and zero bad
areas. Its instantaneous rate varied across the sampled output and was
349 kB/s at the latest complete progress record; average rate at that record
was 22,955 kB/s. The coordinator's earlier 22:22:45 observation was about
8,000 MB at 50.07%, 419 kB/s instantaneous, after an initial rate near
50 MB/s. These are progress samples only; no cause for the rate variation is
established.

For the same interval, the filtered host kernel journal had no matching
`sdb`/USB reset, disconnect, medium-error, `I/O error`, or `Buffer I/O` lines.
Sysfs reported the reader state `running`; `/dev/sdb`, `/dev/sdb1`, and
`/dev/sdb2` each reported kernel read-only state `1`. The block stat snapshot
reported zero writes and two I/Os in progress. These observations do not
establish whole-card readability or physical health. The image was partial at
this snapshot and was not inspected by this audit.

## Completed preservation and read-only checks

The coordinator's GNU ddrescue 1.30 pass began at 22:17:12 and finished at
22:31:04 local. The final map has one `+` range covering byte 0 through
`0x3B8600000` (15,978,201,088 bytes; all 31,207,424 source sectors), with no
remaining, trimmed, scraped, or bad-sector ranges. The command exited 0 and the
final console log reports zero read errors, zero bad areas, and 100% rescued.
The progress rate slowed substantially near 8 GB, then returned to higher
rates as the pass continued; this is observed variation only, with no cause
established. The helper reports image SHA-256
`deb6ed5f9d0bc58906455194a8d02c4b025adffc5f5eb7bd9f10fe56930096e1` and
`all_source_bytes_rescued=true`. See the [rescue report](../../../artifacts/sd-recovery/old-card-backup-001/report.json),
[mapfile](../../../artifacts/sd-recovery/old-card-backup-001/old-pynq-card.map),
and [ddrescue log](../../../artifacts/sd-recovery/old-card-backup-001/ddrescue.log).

Both filesystem checks ran against read-only loop mappings of the preserved
image. `fsck.fat -n -v` on the 130 MiB PYNQ partition exited 1: its FAT dirty
bit is set, while the report says 6 files and 1,848 of 33,241 clusters used.
The checker left the filesystem unchanged. This confirms the unclean FAT state
seen at card insertion; it does not by itself show a media read failure.

`e2fsck -f -n` on the ext4 root partition exited 4 and left reported errors
unfixed. With read-only `-n`, journal recovery was skipped. The log reports a
directory entry under `/var/lib/samba/private/msg.sock` pointing to deleted or
unused inode 780560 with an incorrect file type; unattached inodes 780556 and
780557; and block/inode bitmap and free-count discrepancies. Because recovery
was deliberately skipped and every proposed change was declined, this check
does not show whether journal replay would reconcile any of these findings.
No writable check or repair was run on the source card or preserved image.
See the [FAT check log](../../../artifacts/sd-recovery/old-card-backup-001/partition-1-fsck.log)
and [ext4 check log](../../../artifacts/sd-recovery/old-card-backup-001/partition-2-fsck.log).

Taken together, the evidence establishes filesystem inconsistencies in the
read-only image view and a successful single full read through this host and
USB reader. It does not prove the card healthy, prove a hardware fault, or
attribute the earlier board I/O errors to filesystem metadata alone. The prior
board error, current ext4 findings, and clean host-side read can coexist; the
available evidence does not isolate the cause.

## Safe next evidence

Keep the source card and completed image unchanged. To test journal recovery or
repair effects, make and verify a separate working copy first, then run any
writable checks only on that copy and record their results. The current logs do
not establish post-replay ext4 state or any full-capacity/long-duration media
health guarantee. Further source-card reads should be purpose-limited and
coordinated against the preserved image.

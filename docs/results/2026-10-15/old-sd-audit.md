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
The card's physical health remains unknown. A successful limited read would not
clear that uncertainty.

I performed no filesystem repair, `fsck`, `e2fsck`, `fstrim`, mount, raw scan,
or content read. The coordinator later began a single forward ddrescue image
pass; the sampled progress below is incomplete and does not establish a card
health verdict. No filesystem checks have been reported yet.

## Preservation pass snapshot (in progress)

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
establish whole-card readability or physical health. The image was still
partial at this snapshot and was not inspected by this audit.

## Safe next evidence

Wait for the rescue pass and final mapfile/report. Then run non-writing
filesystem checks against an explicitly read-only loop mapping of the image,
not the source card. Check FAT and ext4 separately and record command exit
status plus `e2fsck -fn` diagnostics. If imaging reports unreadable sectors,
retain the ddrescue mapfile and its ranges; do not infer whole-card health from
successful regions. Any source-card reads beyond the recovery image should be
purpose-limited and coordinated after the image is verified.

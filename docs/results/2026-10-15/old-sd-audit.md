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
evidence that all card sectors are readable. The card was not subjected to a
full read or filesystem check.

The first `dmesg --ctime` attempt failed with `Operation not permitted`.
`journalctl -k` was readable and supplied the insertion evidence above. No
SMART or other media-health telemetry was obtained; the USB bridge identifies
itself only as generic mass storage.

The coordinator reports that unprivileged raw reads of `/dev/sdb` are denied
and `sudo -n` requires interactive authentication. `ddrescue` was not
installed at the time of this audit; the coordinator is preparing a local
extracted package for imaging. This audit did not request interactive sudo or
attempt a raw read.

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

No filesystem repair, `fsck`, `e2fsck`, `fstrim`, mount, raw scan, or content
read was performed here. No execution tests apply to this metadata-only audit.

## Safe next evidence

The parent is preparing a sector image with `ddrescue`; preserve its image and
mapfile before further checking. After the image is complete, run non-writing
filesystem checks against an explicitly read-only loop mapping of the image,
not the source card. Check FAT and ext4 separately and record command exit
status plus `e2fsck -fn` diagnostics. If imaging reports unreadable sectors,
retain the ddrescue mapfile and its ranges; do not infer whole-card health from
successful regions. Any source-card reads beyond the recovery image should be
purpose-limited and coordinated after the image is verified.

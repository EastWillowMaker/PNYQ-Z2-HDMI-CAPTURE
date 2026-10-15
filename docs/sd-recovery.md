# Recover PYNQ on a fresh card and preserve the failing card

The600-second exact HDMI capture result remains valid. The subsequent board
EXT4/read failures and sender SIGBUS require a reliable storage/boot baseline
before further DMA shutdown and interruption qualification. Installing a fresh
official image on a different card avoids carrying the old filesystem state
into that baseline. A fresh image does not, by itself, establish the cause of
the old failure or prove that the board's SD interface/power is healthy.

## Confirmed device identities, 2026-10-15

| Role | Whole device | Size | Identity | Initial partitions |
|---|---|---|---|---|
| New card, intended image target | `/dev/mmcblk0` |62,549,655,552bytes /58.3GiB|SD64G, CID`9f544953443634476194980972018201`|p1 FAT UUID`788A-0755`|
| Old PYNQ card, preserve only | `/dev/sdb` |15,978,201,088bytes /14.9GiB|USB reader000000002958, SCSI0:0:0:1|sdb1 PYNQ FAT UUID`8498-161A`; sdb2 ext4 UUID`40aa3f0d-35f3-47ee-96d1-9fb50b1adbbd`|

Device names may change on reinsertion. Recheck exact identities before each
privileged operation. The new card was initially auto-mounted; the old boot
partition was also auto-mounted read-write by the desktop and was subsequently
unmounted byudisksctl. The old ext4 partition remained unmounted. No raw source
write, repair, or formatting has been performed by the project at this stage.

## Image choice and verified download

The [official boards page](https://www.pynq.io/index.html) lists PYNQ-Z2v3.0.1
andv3.1.1 downloads. Use **v3.0.1** for this recovery baseline because the current
capture code and PynqBuffer ownership tests were validated against that board
runtime. A version upgrade would require a separate compatibility check. The
[official releases](https://github.com/Xilinx/PYNQ/releases) describe3.1's kernel,
tools and overlay updates; do not assume driver/buffer behavior is unchanged.

The page's v3.0.1 link redirects to
[AMD's official archive](https://download.amd.com/opendownload/xlnx/pynq_z2_v3.0.1.zip).
Archive size1,811,523,457bytes; extracted image7,858,807,808bytes. The full ZIP
member was decompressed with CRC verification. Locally computed SHA256:

- ZIP:`ea6372e2d95e241dc7f891d30abc8af2eaf6650c0c16788c27dafba97f41cf8b`
- IMG:`f17405d25298a2c5ea23ccf95f868b42b18f819ff9d7fe5d079ac9ef53415861`

No independently published publisher checksum/signature was retrieved; these
local hashes support subsequent integrity/readback comparisons, while provenance
comes from the official page and HTTPS download. Manifest:
[recovery-image](results/2026-10-15/pynq-z2-recovery-image.json).
Downloads and images stay in ignored`artifacts/sd-recovery/downloads/`.

## Old-card examination

User-requested sub-agent audit is recorded in
[old-sd-audit.md](results/2026-10-15/old-sd-audit.md). The host journal shows an
unclean FAT removal, with no old-card I/O/medium errors recorded during the
initial host session. This is not a physical-health verdict. Raw access requires
local sudo. A failing read-path, logical corruption and board/power/controller
problems remain possible until more evidence is available.

Prepared operator command (local sudo password prompt only):

```sh
sudo /usr/bin/python3 artifacts/operator/preserve-old-pynq-sd.py
```

It guards the exact old-card capacity, partition UUIDs and USB topology, refuses
mounted partitions, sets kernel read-only state, and uses a locally extracted
Ubuntu gddrescue1.30 package. It does not install global packages. One no-retry,
no-trim/no-scrape pass creates a new image and map in
`artifacts/sd-recovery/old-card-backup-001/`; an incomplete map is retained and
filesystem checks are skipped. Only a fully contiguous rescued map enables
FAT/ext4 checks on read-only loop devices over the copy. Each image filesystem
UUID/type is checked before selectingfsck.fat -n ore2fsck -fn.
A complete image with dirty filesystems returns4; it is not a healthy-card result.

The first operator run stopped at identity validation without creating a backup:
lsblk's PATH-only JSON was flat unless--tree was specified. Both inventory calls
now request--tree explicitly; actual device capacity/UUID/mount assertions passed
unprivileged after the correction. No identity check was relaxed.

`e2fsck -n` does not replay the ext4 journal, so journal recovery needs can produce
uncorrected findings. If a later recovery experiment is needed, modify a separate
disposable derivative of the image, preserving the first image/map and original
card. No old-card write stress, fake-capacity test, fsck repair or reimage is
currently authorized or performed.

## New-card image preparation

The entire card is the image target:`/dev/mmcblk0`, **notmmcblk0p1**. A whole-disk
image contains its own partition table and both filesystems. Writing it into an
existing FAT partition is the wrong operation.

Prepared helper default mode performs only identity and image-hash validation:

```sh
/usr/bin/python3 artifacts/operator/flash-new-pynq-sd.py
```

This default check passed on the actual identified new card. The helper requires
an explicit erase flag and local sudo for writing, which has **not yet occurred**:

```sh
sudo /usr/bin/python3 artifacts/operator/flash-new-pynq-sd.py --erase-new-card
```

That command is a proposed destructive step, pending explicit user confirmation.
It replaces the card partition table and writes the first7,858,807,808bytes;
existing partitions/data become unavailable. It is not a secure wipe of all
58.3GiB, and bytes beyond the image remain physically untouched. Before any write it rechecks CID,
model, capacity, original partition identity and local image hash, unmounts only
this card's expected desktop mounts, rechecks state, and opens the whole card
exclusively. It writes the known image, flushes storage, makes the host block
device read-only, then reads every image byte using direct I/O and compares SHA256.
Evidence is written to a new`new-card-flash-001/` directory. A mismatch fails and
must not be reported as a bootable verified card. Its preparation check is not
a test of privileged write/readback or boot behavior, and the8GB image readback
does not certify the card's entire64GB capacity. No permanent host setting changes
are needed; kernel read-only flags clear when the card is removed/reinserted.

After a successful verified write, safely remove the new card and boot PYNQ from
it while powered off for card replacement. Then verify filesystem/storage logs,
PYNQ runtime version and clean shutdown before redeploying017/v10 and repeating
capture/recovery qualification. Preserve the old card and original image.

The new-card helper also received a static sub-agent review; no critical
wrong-target or readback-cache flaw was found. This is source review only, not
proof of privileged execution. It has no interactive prompt beyond its explicit
--erase-new-card flag, so the flag must only be run after the concrete target
overwrite is accepted. The old-card helper was statically reviewed and its
mount/map/partition/result handling tightened before use. Its first actual
identity failure and the corrected nonprivileged check are recorded above.

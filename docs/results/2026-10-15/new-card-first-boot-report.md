# Fresh PYNQ card first boot

The verified official PYNQ-Z2 v3.0.1 image booted from the new SD64G card.
The first boot expanded the ext4 root partition to 62,412,292,096 bytes.
`df` reports a 57 GiB filesystem with about 49 GiB free. PYNQ reports version
3.0.1, Python 3.10.4 and Linux 5.15.19-xilinx-v2022.1. `id`, `lsblk`, `df`,
`ps` and the PYNQ Python import completed without the old command I/O failures.
This is a first-boot result, not the full storage or HDMI qualification.

## Identity and evidence

The board reports SD64G, capacity 62,549,655,552 bytes and serial `0x94980972`,
which match the new host card. Its raw CID ends `...018200`; the host reader
reported `...018201`. The preceding CID fields match. The reason for the last
bit difference has not been verified, so the report preserves both readings.
Do not use the shared image filesystem UUIDs to distinguish the old/new cards.

- `new-card-first-boot.log`: read-only UART capture, through automatic login.
- `new-card-first-boot-summary.json`: 28,269 bytes captured, shell prompt reached,
  no UART input sent, and logger stopped without error.
- `new-card-runtime-baseline.log`: versions, capacity, filesystems and sudo probe.
- `new-card-storage-baseline.log`: resize messages, failed services, mount state,
  card serial and IPv6 address.
- `new-card-services-and-writecheck.log`: service failures and bounded fsync test.

The host restored its existing dedicated `codex-hdmi-m0` Ethernet profile.
Two scoped IPv6 pings to `fe80::200:5ff:fe6b:1a0` passed with zero packet loss.
The Wi-Fi default route remains in use. DHCP server failure does not establish
failure of this observed IPv6 path, nor does a ping prove sustained frame delivery.

## Warnings and limits

The boot log contains `mmc0: Problem switching card into high-speed mode!`.
It then detects the SDXC card and mounts ext4. The actual bus timing/clock has
not been checked. The available resize/kernel/UART evidence shows no recurrence
of the previous EXT4 directory-read/I/O errors, but it is not a full kernel
storage check or proof of media reliability.

`haveged.service` repeatedly exits with SIGSYS and reaches its restart limit.
The IPv4 and IPv6 ISC DHCP server units also report failed. These are observed
stock-image failures and must remain visible in the baseline. Their causes are
not established here. No service configuration was changed to hide the failures.
The journal command also reports an unsupported ACL lookup. Boot includes SPI,
regulatory.db and autofs4 warnings. This report does not classify all warnings
as harmless or claim a completely clean operating system.

A 16 MiB deterministic file was created in the user's cache. The file and parent
directory were fsynced in 3.151 seconds. Its expected SHA256 is
`341aacac661ccb210720bedaa9ead5d668fe5ea41a73532fc147c71e34040df1`.
Persistence will be checked after a normal reboot, so no durability pass is
claimed yet. The file is `/home/xilinx/.cache/hdmi-capture-storage-check.bin`.

The new system requires interactive sudo authentication (`sudo -n` failed).
The next step is full kernel/SD diagnostics and a normal reboot, followed by
checking the persisted test file. No capture overlay or sender was deployed in
this baseline. No new software test run was needed for this evidence-only report.

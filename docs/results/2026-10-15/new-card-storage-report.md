# New PYNQ SD reboot and persistence result

The normal reboot and bounded file persistence check passed on 2026-10-15.
This permits resuming capture experiments. It does not complete M1 or establish
full-card health, power-loss safety or sustained capture stability on this card.

## Executed checks

The operator authenticated on the board UART. The helper then captured full
privileged dmesg and the SD bus state, sent `sudo -n systemctl reboot`, captured
shutdown and the next boot, and checked the previously fsynced 16 MiB file.
The reboot returned to the automatic shell in 49.202 seconds without error.
The boot ID changed from `2719a530-7f3b-42d8-9af9-a6e1d9176ad9` to
`888441ac-9433-48f9-816a-38b40be71c0e`.

The file remained 16,777,216 bytes with SHA256
`341aacac661ccb210720bedaa9ead5d668fe5ea41a73532fc147c71e34040df1`.
All four evidence hashes in `new-card-storage-result.json` were independently
recomputed on the host and matched. The original failed sudo check remains in
`new-card-auth-expired.log`; that attempt sent no reboot.

The UART records unmount-all/shutdown targets, `Restarting system`, a new
U-Boot/Linux startup and a new ext4 root mount. No old EXT4 directory-read,
block I/O or journal-recovery error appears in these captured logs. This is
an observation of this reboot, not a complete offline filesystem inspection.
The post-reboot `/sys/fs/ext4/mmcblk0p2/errors_count` is 0. Normal `df`, `ps`
and network inspection complete. No capture sender was running at that check.

## Retained warnings and scope

Both boots report `Problem switching card into high-speed mode!`. Before the
reboot, `/sys/kernel/debug/mmc0/ios` reports actual clock 25,000,000 Hz,
4-bit bus width and legacy timing. The reason for the high-speed switch failure
is unresolved; no clock, kernel or boot-media setting was changed to suppress it.
This lower-speed mode may affect SD throughput and requires observation under
capture load. The RGB network path uses DDR and TCP; a successful bounded file
check alone does not validate that path.

The fresh boot also retains the U-Boot environment warning, SPI device creation
warning, missing regulatory.db and autofs4 warning. The post-reboot failed-unit
list contains both ISC DHCP server units. The earlier haveged SIGSYS failure
remains historical evidence; haveged is absent from this post-reboot failed-unit
list. These results do not establish its cause or prove permanent recovery.

No overlay or capture sender was loaded for this storage check. The test file
is retained in `/home/xilinx/.cache/hdmi-capture-storage-check.bin`. Next: stage
the unchanged 017/v10 artifacts, run a fresh KMS capture experiment, and require
explicit DMA-halted/buffer-release evidence plus post-run storage checks.
Source interruption, reconnect and unsupported-mode tests remain separate.
No software implementation changed and no hosted CI was run for this report.

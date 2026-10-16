# Board passwordless sudo

Installed and verified on 2026-10-16. Both the initial check and a separate UART
check returned UID `0` from `sudo -k -n id -u`; `visudo -c` passed and the rule
file was owned by `root:root` with mode `0440`. See the
[installation log](results/2026-10-16/board-sudo-install.log) and
[independent verification](results/2026-10-16/board-sudo-verify.log).

The accepted next scope grants the board's `xilinx` account passwordless sudo
for all commands. The account's login password remains unchanged. The host PC
sudo configuration is not modified.

Copy `tools/configure_board_sudo.sh` to the board and inspect it before running
it there with `sudo sh configure_board_sudo.sh`. Initial authentication, if
needed, happens only at the board's local password prompt. The script requires
root on an `armv7l` host named `pynq`, checks the existing sudo configuration,
and refuses to replace an existing `/etc/sudoers.d/99-codex-xilinx` file. It
validates the new rule before installation and checks the full configuration
afterward, removing the new rule if that final validation fails.

The installed rule is:

```sudoers
xilinx ALL=(ALL:ALL) NOPASSWD: ALL
```

From the normal `xilinx` shell, run `sudo -k -n id -u`. A successful result of
`0` verifies elevation without relying on a cached password. Inspect
`sudo -n -l` to confirm the rule is active. To revert this change, remove only
`/etc/sudoers.d/99-codex-xilinx` as root and run `visudo -c`; the account's other
sudo rules remain in effect.

The rule grants root access to anyone who can execute commands as `xilinx`.
It does not make capture DMA shutdown safe or authorize force-killing a native
capture process. Continue to use the capture preparation and safe-halt checks.

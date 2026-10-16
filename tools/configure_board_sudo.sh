#!/bin/sh
# Run as root on the PYNQ board after local authentication.
set -eu

if [ "$(id -u)" != 0 ] || [ "$(hostname)" != pynq ] || [ "$(uname -m)" != armv7l ]; then
    echo 'Expected root on the armv7l PYNQ board; no changes made' >&2
    exit 1
fi
id xilinx >/dev/null
target=/etc/sudoers.d/99-codex-xilinx
rule='xilinx ALL=(ALL:ALL) NOPASSWD: ALL'
/usr/sbin/visudo -c
if [ -e "$target" ] || [ -L "$target" ]; then
    echo "Refusing to replace existing $target; inspect it first" >&2
    exit 1
fi
candidate=$(mktemp /etc/sudoers.d/.codex-xilinx-XXXXXX)
trap 'rm -f "$candidate"' EXIT HUP INT TERM
printf '%s\n' "$rule" > "$candidate"
chown root:root "$candidate"
chmod 0440 "$candidate"
/usr/sbin/visudo -cf "$candidate"
mv "$candidate" "$target"
if ! /usr/sbin/visudo -c; then
    rm -f "$target"
    echo 'Validation failed; removed the new rule' >&2
    exit 1
fi
echo "Installed $target; verify from the xilinx account with sudo -k -n id -u"

#!/bin/bash
# Set up the system parts of a fresh install: apps, system fixes from files/,
# GRUB, and the initramfs. Run on a fresh install once the T2 kernel is on
# (https://wiki.t2linux.org/), then run ./setup-desktop.sh as yourself.
# Safe to run again. Run with: sudo ./setup-system.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

cd "$(dirname "$0")/files"

put() {
    install -v -D -m "$1" "$2" "/$2"
}

#
# Apps
#

# VS Code, the way https://code.visualstudio.com/docs/setup/linux says
if [ ! -e /etc/apt/sources.list.d/vscode.sources ]; then
    wget -qO- https://packages.microsoft.com/keys/microsoft.asc |
        gpg --dearmor --yes -o /usr/share/keyrings/microsoft.gpg
    chmod 644 /usr/share/keyrings/microsoft.gpg
    cat >/etc/apt/sources.list.d/vscode.sources <<'EOF'
Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Architectures: amd64
Signed-By: /usr/share/keyrings/microsoft.gpg
EOF
fi

apt-get update
# libamdhip64-7 and rocminfo are for Blender, see blender-gpu.md
apt-get install -y code ghostty libamdhip64-7 rocminfo
snap install blender --channel=5.2lts/stable --classic

# Fewer locales to regenerate on libc upgrades, see locales.md
apt-get purge -y '?name("^language-pack-(gnome-)?(de|es|fr|it|pt|ru|zh-hans)(-base)?$")'

#
# System fixes
#

# USB-C hotplug, see README.md
put 644 etc/udev/rules.d/90-t2-usbc-hotplug.rules

# The Intel GPU drives the screen and GNOME, and the console stays visible
put 644 etc/modprobe.d/apple-gmux.conf
put 644 etc/udev/rules.d/61-mutter-primary-gpu.rules
put 644 etc/udev/rules.d/90-console-on-igpu.rules

# Lid close suspends, also after waking with the lid closed, see
# wake-with-lid-closed.md
put 644 etc/systemd/logind.conf.d/lid-inhibit.conf

# Automatic upgrades on battery, see auto-upgrades.md
put 644 etc/systemd/system/apt-daily.service.d/on-battery.conf
put 644 etc/systemd/system/apt-daily-upgrade.service.d/on-battery.conf
put 644 etc/apt/apt.conf.d/51unattended-upgrades-on-battery
put 755 etc/NetworkManager/dispatcher.d/90-apt-daily

# Not amdgpu-off: suspend hangs with the Radeon off, see suspend-notes.md

systemctl daemon-reload
udevadm control --reload

#
# GRUB: menu with all kernels, readable font, boot messages instead of splash
#

put 644 etc/default/grub.d/90-menu-timeout.cfg
put 644 etc/default/grub.d/91-no-splash.cfg
grub-mkfont -s 24 -o /boot/grub/fonts/dejavu-mono-24.pf2 \
    /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
update-grub

#
# Initramfs: T2 keyboard for the disk password, and quick wakeup from suspend
# through the Thunderbolt ACPI override, see suspend-notes.md
#

put 644 etc/dracut.conf.d/90-cryptroot.conf
put 644 etc/dracut.conf.d/92-t2-acpi-override.conf
put 644 usr/local/lib/acpi-override/tbt-peg12.aml

# The disk password in the initramfs, only if its key file has been made
if [ -e /etc/cryptsetup-keys.d/cryptroot.key ]; then
    put 644 etc/dracut.conf.d/91-cryptroot-key.conf
else
    echo "No /etc/cryptsetup-keys.d/cryptroot.key, the disk password will be asked for at boot"
fi

# Every kernel, so the fallback ones in the GRUB menu work too
FAILED=
for VMLINUZ in /boot/vmlinuz-*; do
    KVER=${VMLINUZ#/boot/vmlinuz-}
    INITRD=/boot/initrd.img-$KVER

    # Keep the first backup; don't overwrite a known-good one on re-runs
    if [ -e "$INITRD" ]; then
        cp -av --update=none "$INITRD" "$INITRD.bak"
    fi

    dracut --force --kver "$KVER"

    # The kernel only picks up ACPI tables from the early, uncompressed part
    CONTENTS=$(lsinitrd "$INITRD")
    if ! grep -q 'kernel/firmware/acpi/tbt-peg12.aml' <<<"$CONTENTS"; then
        echo "PROBLEM: tbt-peg12.aml is not in $INITRD" >&2
        FAILED=1
    fi

    # Without the T2 driver there's no keyboard for typing the disk password
    DRIVERS=$(lsinitrd -f etc/cmdline.d/20-force_drivers.conf "$INITRD" || true)
    if ! grep -qE 'rd.driver.pre=(t2bce_vhci|apple_bce)' <<<"$DRIVERS"; then
        echo "PROBLEM: no T2 keyboard driver force-loaded in $INITRD" >&2
        echo "Check /etc/dracut.conf.d/90-cryptroot.conf" >&2
        FAILED=1
    fi
done

if [ -n "$FAILED" ]; then
    echo "Old initramfs files are in /boot/*.bak" >&2
    exit 1
fi

echo "OK. Run ./setup-desktop.sh as yourself, then reboot."

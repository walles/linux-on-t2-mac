#!/bin/bash
# Install the USB-C hotplug and Thunderbolt ACPI fixes from files/,
# then rebuild the initramfs. Run with: sudo ./install-fixes.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

cd "$(dirname "$0")/files"

KVER=$(uname -r)
INITRD=/boot/initrd.img-$KVER

if [ ! -e "$INITRD" ]; then
    echo "$INITRD not found" >&2
    exit 1
fi

install -v -m644 etc/udev/rules.d/90-t2-usbc-hotplug.rules /etc/udev/rules.d/
install -v -m644 etc/dracut.conf.d/92-t2-acpi-override.conf /etc/dracut.conf.d/
install -v -D -m644 usr/local/lib/acpi-override/tbt-peg12.aml \
    /usr/local/lib/acpi-override/tbt-peg12.aml

# Keep the first backup; don't overwrite a known-good one on re-runs
if [ ! -e "$INITRD.bak" ]; then
    cp -av "$INITRD" "$INITRD.bak"
fi

dracut --force --kver "$KVER"

# The kernel only picks up ACPI tables from the early, uncompressed part
CONTENTS=$(lsinitrd "$INITRD")
if ! grep -q 'kernel/firmware/acpi/tbt-peg12.aml' <<<"$CONTENTS"; then
    echo "PROBLEM: tbt-peg12.aml is not in $INITRD" >&2
    echo "Old initramfs is at $INITRD.bak" >&2
    exit 1
fi

# Without the T2 driver there's no keyboard for typing the disk password
DRIVERS=$(lsinitrd -f etc/cmdline.d/20-force_drivers.conf "$INITRD" || true)
if ! grep -qE 'rd.driver.pre=(t2bce_vhci|apple_bce)' <<<"$DRIVERS"; then
    echo "PROBLEM: no T2 keyboard driver force-loaded in $INITRD" >&2
    echo "Check /etc/dracut.conf.d/90-cryptroot.conf" >&2
    echo "Old initramfs is at $INITRD.bak" >&2
    exit 1
fi

echo "OK. Reboot to test."

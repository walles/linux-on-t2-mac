#!/bin/bash
# Install the trackpad and USB-C hotplug fixes from files/, then rebuild the
# initramfs. Run with: sudo ./install-fixes.sh
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

install -v -m644 etc/dracut.conf.d/89-t2-trackpad.conf /etc/dracut.conf.d/
install -v -m644 etc/udev/rules.d/90-t2-usbc-hotplug.rules /etc/udev/rules.d/

# Keep the first backup; don't overwrite a known-good one on re-runs
if [ ! -e "$INITRD.bak" ]; then
    cp -av "$INITRD" "$INITRD.bak"
fi

dracut --force --kver "$KVER"

# bcm5974 must be force-loaded before apple_bce brings up the internal USB bus
echo
echo "Force-loaded drivers in the new initramfs, in load order:"
DRIVERS=$(lsinitrd -f etc/cmdline.d/20-force_drivers.conf "$INITRD" | grep -o 'rd.driver.pre=[^ ]*' || true)
echo "$DRIVERS"
if echo "$DRIVERS" | grep -A100 -x 'rd.driver.pre=bcm5974' | grep -qx 'rd.driver.pre=apple_bce'; then
    echo
    echo "OK: bcm5974 loads before apple_bce. Reboot to test."
else
    echo
    echo "PROBLEM: expected rd.driver.pre=bcm5974 before rd.driver.pre=apple_bce" >&2
    echo "Old initramfs is at $INITRD.bak" >&2
    exit 1
fi

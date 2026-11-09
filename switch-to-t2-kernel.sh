#!/bin/bash
# Install the T2 kernel, keeping the current Ubuntu kernel bootable as a
# fallback from the GRUB menu. Run from the Ubuntu kernel with the t2linux
# DKMS modules, set up as in https://wiki.t2linux.org/.
#
# Run as: sudo ./switch-to-t2-kernel.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run this with sudo" >&2
  exit 1
fi

# The running kernel becomes the fallback
OLD_KERNEL=$(uname -r)
if [[ $OLD_KERNEL == *-t2* ]]; then
  echo "Already running the T2 kernel $OLD_KERNEL" >&2
  exit 1
fi

# A newer Ubuntu kernel that hasn't been booted would lose its DKMS modules
# below without a backup, and then be listed first among the fallbacks
NEWEST=$(find /boot -maxdepth 1 -name 'vmlinuz-*' ! -name '*-t2-*' -printf '%f\n' |
  sed 's/^vmlinuz-//' | sort -V | tail -n1)
if [[ $NEWEST != "$OLD_KERNEL" ]]; then
  echo "Reboot into the newest kernel, $NEWEST, first" >&2
  exit 1
fi

cd "$(dirname "$0")"

# Upgrading the linux-t2 0.1 placeholder runs its prerm, which does
# "dkms remove --all" on apple-bce and friends. Keep copies of the modules
# where dkms doesn't look. updates/ outranks the stock modules
# (/etc/depmod.d/ubuntu.conf) and dkms only touches updates/dkms/.
# Empty on a re-run, if the modules were removed last time.
if compgen -G "/lib/modules/$OLD_KERNEL/updates/dkms/*.ko.zst" >/dev/null; then
  mkdir -p "/lib/modules/$OLD_KERNEL/updates/t2-backup"
  cp "/lib/modules/$OLD_KERNEL"/updates/dkms/*.ko.zst \
    "/lib/modules/$OLD_KERNEL/updates/t2-backup/"
fi

# Remove the DKMS modules ourselves, so they can't get built for the T2 kernel
# whatever order apt runs things in. The T2 kernel has its own versions.
for NAME in apple-bce bcm5974-t2 applesmc-t2 linux-apfs-rw; do
  # Lines look like "apple-bce/0.2, 7.0.0-30-generic, x86_64: installed".
  # Nothing if this script has been run before.
  for MODULE in $(dkms status -m "$NAME" | grep -o "^$NAME/[^,:]*" | sort -u); do
    dkms remove "$MODULE" --all
  done
done
depmod "$OLD_KERNEL"

# Load t2bce on the T2 kernel, apple-bce on the Ubuntu kernel
cp files/etc/dracut.conf.d/90-cryptroot.conf /etc/dracut.conf.d/

# The meta packages that pull in new Ubuntu kernels, like linux-generic-hwe-26.04
# or linux-image-generic. Without DKMS those would boot with no keyboard or
# trackpad. Removing them keeps the fallback kernel, it's just no longer
# upgraded.
mapfile -t METAS < <(
  dpkg-query -W -f '${db:Status-Abbrev} ${Package}\n' \
    'linux-generic*' 'linux-image-generic*' 'linux-headers-generic*' 2>/dev/null |
    awk '$1 == "ii" { print $2 }'
)

# Only the kernel, no full upgrade. Newer T2 kernels come with linux-t2
# upgrades from /etc/apt/sources.list.d/t2.list. The trailing "-" removes.
apt install linux-t2 "${METAS[@]/%/-}"

# Don't let apt autoremove the fallback kernel. The removed meta packages were
# also what kept CPU microcode updates and thermal management installed.
apt-mark manual "linux-image-$OLD_KERNEL" "linux-modules-$OLD_KERNEL" \
  intel-microcode thermald

# Rebuild the fallback initramfs, so it's made the same way it would be next
# time and we know that works. Keep the one we know boots, just in case.
cp --update=none "/boot/initrd.img-$OLD_KERNEL" "/boot/initrd.img-$OLD_KERNEL.pre-t2"
dracut --force "/boot/initrd.img-$OLD_KERNEL" "$OLD_KERNEL"

# The newest T2 kernel, the one linux-t2 just installed
NEW_KERNEL=$(find /boot -maxdepth 1 -name 'vmlinuz-*-t2-*' -printf '%f\n' |
  sed 's/^vmlinuz-//' | sort -V | tail -n1)
if [[ -z $NEW_KERNEL ]]; then
  echo "PROBLEM: no T2 kernel in /boot after installing linux-t2" >&2
  exit 1
fi

# Show all checks even if one fails
set +e +o pipefail

for KERNEL in $NEW_KERNEL $OLD_KERNEL; do
  echo
  echo "=== $KERNEL initramfs, want t2bce_vhci or apple_bce:"
  lsinitrd -f etc/cmdline.d/20-force_drivers.conf "/boot/initrd.img-$KERNEL"
  echo "=== $KERNEL initramfs, want the driver modules and cryptroot.key:"
  lsinitrd "/boot/initrd.img-$KERNEL" |
    grep -E 't2bce|apple-bce|cryptroot.key' | awk '{print $NF}'
done

echo
echo "=== $OLD_KERNEL apple-bce module, want a path under updates/t2-backup:"
modinfo -k "$OLD_KERNEL" -n apple-bce

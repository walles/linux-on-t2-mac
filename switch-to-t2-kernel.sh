#!/bin/bash
# Install the T2 kernel, keeping the current Ubuntu kernel bootable as a
# fallback from the GRUB menu.
#
# Run as: sudo ./switch-to-t2-kernel.sh

set -euo pipefail

OLD_KERNEL=7.0.0-30-generic
NEW_KERNEL=7.2.8-1-t2-resolute

if [[ $EUID -ne 0 ]]; then
  echo "Run this with sudo" >&2
  exit 1
fi

cd "$(dirname "$0")"

# Upgrading the linux-t2 0.1 placeholder runs its prerm, which does
# "dkms remove --all" on apple-bce and friends. Keep copies of the modules
# where dkms doesn't look. updates/ outranks the stock modules
# (/etc/depmod.d/ubuntu.conf) and dkms only touches updates/dkms/.
if [[ -d /lib/modules/$OLD_KERNEL/updates/dkms ]]; then
  mkdir -p /lib/modules/$OLD_KERNEL/updates/t2-backup
  cp /lib/modules/$OLD_KERNEL/updates/dkms/*.ko.zst \
    /lib/modules/$OLD_KERNEL/updates/t2-backup/
fi

# Remove the DKMS modules ourselves, so they can't get built for the T2 kernel
# whatever order apt runs things in. The T2 kernel has its own versions.
for MODULE in apple-bce/0.2 bcm5974-t2/0.1 applesmc-t2/0.1 linux-apfs-rw/0.1; do
  # Already gone if this script has been run before
  if [[ -n $(dkms status "$MODULE") ]]; then
    dkms remove "$MODULE" --all
  fi
done
depmod $OLD_KERNEL

# Load t2bce on the T2 kernel, apple-bce on the Ubuntu kernel
cp files/etc/dracut.conf.d/89-t2-trackpad.conf \
  files/etc/dracut.conf.d/90-cryptroot.conf \
  /etc/dracut.conf.d/

# Only the kernel, no full upgrade. Newer T2 kernels come with linux-t2
# upgrades from /etc/apt/sources.list.d/t2.list.
#
# The trailing "-" removes the meta packages that pull in new Ubuntu kernels.
# Without DKMS those would boot with no keyboard or trackpad. This keeps the
# fallback kernel, it's just no longer upgraded.
apt install linux-t2 \
  linux-generic-hwe-24.04- linux-generic-hwe-26.04- \
  linux-image-generic-hwe-26.04- linux-headers-generic-hwe-26.04-

# The upgrade deletes this, it belonged to the linux-t2 0.1 placeholder
cp files/etc/modprobe.d/9027.conf /etc/modprobe.d/

# Don't let apt autoremove the fallback kernel. The removed meta packages were
# also what kept CPU microcode updates and thermal management installed.
apt-mark manual linux-image-$OLD_KERNEL linux-modules-$OLD_KERNEL \
  intel-microcode thermald

# Rebuild the fallback initramfs, so it's made the same way it would be next
# time and we know that works. Keep the one we know boots, just in case.
cp --update=none /boot/initrd.img-$OLD_KERNEL /boot/initrd.img-$OLD_KERNEL.pre-t2
dracut --force /boot/initrd.img-$OLD_KERNEL $OLD_KERNEL

# The T2 initramfs was built during apt install, before 9027.conf was back
dracut --force /boot/initrd.img-$NEW_KERNEL $NEW_KERNEL

# Show all checks even if one fails
set +e +o pipefail

for KERNEL in $NEW_KERNEL $OLD_KERNEL; do
  echo
  echo "=== $KERNEL initramfs, want bcm5974 first, then t2bce_vhci or apple_bce:"
  lsinitrd -f etc/cmdline.d/20-force_drivers.conf /boot/initrd.img-$KERNEL
  echo "=== $KERNEL initramfs, want the driver modules and cryptroot.key:"
  lsinitrd /boot/initrd.img-$KERNEL |
    grep -E 't2bce|apple-bce|bcm5974|cryptroot.key' | awk '{print $NF}'
done

echo
echo "=== $OLD_KERNEL apple-bce module, want a path under updates/t2-backup:"
modinfo -k $OLD_KERNEL -n apple-bce

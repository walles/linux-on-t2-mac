# Disk Encryption

Goal: full disk encryption that holds up for work use, with a single password
typed at boot.

Status: not needed yet, work happens in macOS, where FileVault is on. Do this
before moving work to Linux.

## Current state

The root filesystem is LUKS encrypted (`cryptroot` on `vg0/root`), but the
password is a dummy, and `files/etc/dracut.conf.d/91-cryptroot-key.conf` puts
it in the initramfs on the unencrypted `/boot`. Anyone holding the disk can
unpack the initramfs, read `cryptroot.key` and open the volume. That makes it
as good as unencrypted.

## Threat model

- **Stolen or lost while powered off**: the case that matters, also for
  compliance. A lost laptop with work data on it may be a reportable GDPR
  breach unless the disk can't be read without a secret the thief doesn't
  have. A real LUKS password covers this.
- **Stolen while suspended**: the key is in RAM, so the GNOME lock screen is
  the barrier. Thunderbolt DMA is blocked by `intel_iommu=on`. Cold boot
  attacks are possible in theory but unlikely for a stolen laptop.
- **Evil maid**, someone tampers with `/boot` and waits for the password to be
  typed: out of scope. Booting Linux needs the T2 Secure Boot set to "No
  Security", and Linux can't use the T2 as a TPM, so there's no measured boot
  that could notice a modified initramfs.

Before moving work here, ask IT what they actually require. "Disk encryption
on" is covered by this plan. MDM compliance checks (Intune for Linux, for
example) may have other requirements, like supported distro versions.

## Password strength

Unlike FileVault on a T2 Mac, LUKS has no hardware rate limiting. An attacker
can copy the LUKS header and guess offline on as much hardware as they like.
The only things slowing them down are the password and the key derivation
function. LUKS2 defaults to Argon2id, tuned to take about 2 s and up to 1 GB of
RAM per guess on the machine that created the key slot, which hurts GPUs a lot.
Even so, the password has to carry the strength by itself: at least five
random words from a word list (diceware), not a reused or human made up one.

The current key slot is LUKS2 with Argon2id, 1 GiB of memory and time cost 7
(`sudo cryptsetup luksDump /dev/mapper/vg0-root`, checked 2026-11-11).
`luksChangeKey` benchmarks again and writes a new key slot, so check again
after changing the password.

## Switching to a real password

1. Remove the key from the initramfs:
   `sudo rm /etc/cryptsetup-keys.d/cryptroot.key /etc/dracut.conf.d/91-cryptroot-key.conf`,
   and drop the key file instructions from `README.md`.
2. Replace the dummy password:
   `sudo cryptsetup luksChangeKey /dev/mapper/vg0-root`. Older initramfs
   images in `/boot` still contain the dummy password, but it no longer opens
   anything after this.
3. Rebuild the initramfs: `sudo dracut --regenerate-all --force`.
4. Reboot and check that the password is asked for, and that the internal
   keyboard works at the prompt.

## Single password login with GDM autologin

Typing the disk password and then the login password is annoying. GNOME's
answer is GDM autologin, with the disk password reused to unlock the GNOME
keyring:

- `systemd-cryptsetup` puts the password it unlocked the disk with in the
  kernel keyring, as a key named `cryptsetup`.
- With autologin, GDM runs the `/etc/pam.d/gdm-autologin` stack. Ubuntu's
  already has `pam_gdm.so`, which reads that `cryptsetup` key and hands it to
  `pam_gnome_keyring.so` next in the stack. systemd's `pam_systemd_loadkey.so`
  (installed, systemd 259) does the same job, in case `pam_gdm.so` doesn't.
- Turn on autologin in Settings → System → Users, or with
  `AutomaticLoginEnable=true` and `AutomaticLogin=johan` under `[daemon]` in
  `/etc/gdm3/custom.conf`.
- For the keyring to unlock, the login password must be the same as the disk
  password. If they differ, the keyring stays locked and asks on first use.

None of this is tested here yet. Things to verify:

- The `cryptsetup` key survives from the dracut initramfs into the real root
  and is still there when GDM starts (`sudo keyctl show @u` as root, early
  after boot).
- The GNOME keyring is unlocked after autologin (Firefox and Ghostty don't
  ask for a keyring password).
- The lock screen after suspend still asks for the user password.

## Alternatives

- **TPM unlock**: not possible, Linux doesn't get a TPM on T2 Macs.
- **FIDO2 key**: `systemd-cryptenroll --fido2-device=auto` adds a key slot
  unlocked by touching a YubiKey or similar. Keep the password slot as a
  fallback.

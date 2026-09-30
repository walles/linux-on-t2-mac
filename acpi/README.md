# ACPI table overrides

The kernel loads the tables in `/usr/local/lib/acpi-override/` from the
initramfs at boot, in place of the firmware tables with the same OEM ID and
OEM table ID. Nothing is written to the firmware. Remove
`/etc/dracut.conf.d/92-t2-acpi-override.conf` and rebuild the initramfs to go
back to the firmware tables.

## tbt-peg12.aml

The Thunderbolt table, SSDT `APPLE TbtPEG12`, with the timeouts in `CRMW`,
`CIOR` and `CIOW` shortened. See `tbt-peg12.patch`.

When a Thunderbolt bridge or NHI powers up, its `_PS0` calls `CRMW` to set a
bit in a Thunderbolt switch register, through a mailbox in the bridge's PCI
config space. Under Linux the mailbox never answers. Each `CIOR` polled it
10000 times with `Stall (25)`, 0.44s in practice, and `CRMW` tried 5 times
with `Sleep (100)` between, so each `CRMW` took 2.7s and wrote nothing. There
are three `CRMW` calls per controller, so waking up from suspend took about
16s longer than it has to. Now it polls 400 times and tries once.

To rebuild it, with `acpica-tools` installed:

```
sudo cat /sys/firmware/acpi/tables/SSDT12 >SSDT12.aml
iasl -d SSDT12.aml
patch SSDT12.dsl tbt-peg12.patch
iasl -p tbt-peg12 SSDT12.dsl
```

Check that SSDT12 is still `TbtPEG12` first, with `iasl -d`. If the firmware
table's OEM revision gets bumped past 0x1001, the kernel will ignore the
override.

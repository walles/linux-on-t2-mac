#!/bin/sh
# Power the first Thunderbolt controller down at runtime and time powering it
# back up, to see whether its ACPI _PS0 is slow without any suspend. Traces
# the ACPI methods run while waking up into the kernel log. Run with sudo.
#
# The NHI stays awake with the thunderbolt driver bound, and also without a
# driver, so it gets removed for the test and found again by a rescan at the
# end.
P=/sys/bus/pci/devices/0000
A=/sys/module/acpi/parameters

show() {
  for d in 00:01.1 06:00.0 07:00.0 07:02.0 08:00.0 09:00.0; do
    if [ -e $P:$d ]; then
      echo "  $d $(cat $P:$d/power/runtime_status) $(cat $P:$d/power_state)"
    else
      echo "  $d removed"
    fi
  done
}

echo 'Before:'
show

echo 1 >$P:08:00.0/remove
# The udev rule 90-t2-usbc-hotplug.rules keeps the xHCI on, which keeps the
# whole chain powered
echo auto >$P:09:00.0/power/control
echo 'Waiting up to 60s for the Thunderbolt chain to power down'
for i in $(seq 60); do
  [ "$(cat $P:00:01.1/power/runtime_status)" = suspended ] && break
  sleep 1
done
echo 'Powered down:'
show

# Log the start and end of every ACPI method while waking up
echo enable >$A/trace_state
# Writing "on" resumes the xHCI and its parents before it returns
start=$(date +%s.%N)
echo on >$P:09:00.0/power/control
end=$(date +%s.%N)
echo disable >$A/trace_state
echo 'Back up:'
show
echo "Powering up the xHCI and its bridges took $(awk "BEGIN { print $end - $start }")s"

start=$(date +%s.%N)
echo 1 >/sys/bus/pci/rescan
end=$(date +%s.%N)
echo 'After the rescan:'
show
echo "The rescan took $(awk "BEGIN { print $end - $start }")s"

#!/bin/sh
# read-only: list USB sysfs layout (no device opened)
uname -r
for d in /sys/bus/usb/devices/usb*; do
  echo "== $d -> $(readlink -f $d)"
  echo "speed=$(cat $d/speed) maxchild=$(cat $d/maxchild) version=$(cat $d/version) busnum=$(cat $d/busnum) devpath=$(cat $d/devpath) product=$(cat $d/product)"
  n=$(basename $d); b=${n#usb}
  for p in $d/$b-0:1.0/usb$b-port*; do
    [ -e "$p" ] || continue
    printf '%s: ' "$(basename $p)"; for a in connect_type location state disable quirks over_current_count; do printf '%s=%s ' $a "$(cat $p/$a 2>&1 | tr '\n' ' ')"; done
    [ -e $p/peer ] && printf 'peer=%s ' "$(basename $(readlink $p/peer))"; [ -e $p/device ] && printf 'device=%s' "$(basename $(readlink $p/device))"; [ -d $p/physical_location ] && printf ' physloc=yes'; echo
  done | head -6
  ls -l $p 2>/dev/null | head -3
done
ls -ld /sys/kernel/debug; stat -c '%a %U %n' /sys/firmware/acpi/tables 2>&1
echo "dmesg_restrict=$(cat /proc/sys/kernel/dmesg_restrict)"

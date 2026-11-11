#!/bin/sh
# read-only: show sysfs endpoint attribute formats and permissions (verifier, 2026-11-06)
id -u
d=/sys/bus/usb/devices/usb1/1-0:1.0/ep_81
for a in bInterval interval wMaxPacketSize type direction; do printf '%s=%s\n' "$a" "$(cat $d/$a)"; done
printf 'bAlternateSetting=%s\n' "$(cat /sys/bus/usb/devices/usb1/1-0:1.0/bAlternateSetting)"
stat -c '%a %n' /sys/bus/usb/devices/usb1/descriptors /sys/bus/usb/devices/usb1/1-0:1.0/usb1-port1/connect_type /sys/bus/usb/devices/usb1/1-0:1.0/usb1-port1/location

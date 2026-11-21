#!/bin/sh
# Modified by Lululla - 2026-11-21: POSIX shell, shebang
# Create /dev/kernel pointing to the kernel partition given on the kernel
# command line (kernel=/dev/mmcblkXpY).
for arg in $(cat /proc/cmdline) ; do
    key=${arg%%=*}
    value=${arg#*=}
    if [ "$key" = "kernel" ] ; then
        ln -sf "$value" /dev/kernel
    fi
done

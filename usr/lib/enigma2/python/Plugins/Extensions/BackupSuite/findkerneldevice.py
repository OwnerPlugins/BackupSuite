# -*- coding: utf-8 -*-
#
# Finds the eMMC kernel partition (GPT) and links it to /dev/kernel.
# Modified by Lululla - 2026-11-21: no side effects on import, PARTNAME lookup fixed
#

import os
import collections
import struct
import uuid
import re

# GPT header and partition formats
GPT_HEADER_FORMAT = """
8s signature
4s revision
L header_size
L crc32
4x _
Q current_lba
Q backup_lba
Q first_usable_lba
Q last_usable_lba
16s disk_guid
Q part_entry_start_lba
L num_part_entries
L part_entry_size
L crc32_part_array
"""

GPT_PARTITION_FORMAT = """
16s type
16s unique
Q first_lba
Q last_lba
Q flags
72s name
"""


def _make_fmt(name, format, extras=[]):
    type_and_name = [line.split(None, 1)
                     for line in format.strip().splitlines()]
    fmt = "<" + "".join(t for t, _ in type_and_name)
    fields = [n for t, n in type_and_name if n != "_"] + extras
    tupletype = collections.namedtuple(name, fields)
    return fmt, tupletype


class GPTError(Exception):
    pass


def read_header(fp, lba_size=512):
    fp.seek(1 * lba_size)  # skip protective MBR
    fmt, GPTHeader = _make_fmt("GPTHeader", GPT_HEADER_FORMAT)
    data = fp.read(struct.calcsize(fmt))
    header = GPTHeader._make(struct.unpack(fmt, data))
    if header.signature != b"EFI PART":
        raise GPTError("Bad signature: {0!r}".format(header.signature))
    if header.revision != b"\x00\x00\x01\x00":
        raise GPTError("Bad revision: {0!r}".format(header.revision))
    if header.header_size < 92:
        raise GPTError("Bad header size: {0!r}".format(header.header_size))
    return header._replace(
        disk_guid=str(uuid.UUID(bytes_le=header.disk_guid))
    )


def read_partitions(fp, header, lba_size=512):
    fp.seek(header.part_entry_start_lba * lba_size)
    fmt, GPTPartition = _make_fmt(
        "GPTPartition", GPT_PARTITION_FORMAT, extras=["index"])
    for idx in range(1, 1 + header.num_part_entries):
        data = fp.read(header.part_entry_size)
        if len(data) < struct.calcsize(fmt):
            raise GPTError("Short partition entry")
        part = GPTPartition._make(struct.unpack(fmt, data) + (idx,))
        if part.type == b"\x00" * 16:
            continue
        part = part._replace(
            type=str(uuid.UUID(bytes_le=part.type)),
            unique=str(uuid.UUID(bytes_le=part.unique)),
            name=part.name.decode("utf-16").split("\x00", 1)[0]
        )
        yield part


def find_kernel_device_udevadm(kernelpartition):
    """Look the partition up by its PARTNAME in sysfs (no udevadm needed)."""
    try:
        for partition in sorted(os.listdir("/sys/block/mmcblk0")):
            if not partition.startswith("mmcblk0p"):
                continue
            uevent = "/sys/block/mmcblk0/{0}/uevent".format(partition)
            try:
                with open(uevent, "r") as f:
                    for line in f:
                        if line.strip() == "PARTNAME={0}".format(
                                kernelpartition):
                            return "/dev/{0}".format(partition)
            except (IOError, OSError):
                continue
        return ""
    except Exception:
        return ""


def find_kernel_device_gpt(kernelpartition):
    device = "/dev/mmcblk0"
    try:
        with open("/proc/cmdline", "r") as f:
            match = re.search(r"/dev/mmcblk\d+", f.read())
            if match:
                device = match.group(0)
    except Exception:
        pass
    try:
        with open(device, "rb") as f:
            header = read_header(f)
        with open(device, "rb") as f:
            for p, part in enumerate(read_partitions(f, header), start=1):
                if kernelpartition == part.name:
                    return "{0}p{1}".format(device, p)
        return ""
    except Exception:
        return ""


def main():
    """Create the /dev/kernel symlink for the running kernel partition."""
    try:
        with open("/sys/firmware/devicetree/base/chosen/kerneldev", "r") as f:
            kerneldev = f.readline().split(".")
    except (IOError, OSError):
        return 1
    if len(kerneldev) < 2 or "emmcflash0" not in kerneldev[0]:
        return 1
    partition_name = kerneldev[1].strip("\0").strip()
    kerneldevice = find_kernel_device_udevadm(partition_name)
    if not kerneldevice:
        kerneldevice = find_kernel_device_gpt(partition_name)
    if not kerneldevice:
        return 1
    try:
        if os.path.islink("/dev/kernel") or os.path.exists("/dev/kernel"):
            os.remove("/dev/kernel")
        os.symlink(kerneldevice, "/dev/kernel")
    except OSError:
        return 1
    return 0


# Only run when executed by the backup script, never on import
if __name__ == "__main__":
    import sys
    sys.exit(main())

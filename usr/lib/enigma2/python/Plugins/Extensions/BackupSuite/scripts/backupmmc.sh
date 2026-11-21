#!/bin/sh
# BackupSuite for Enigma2 - launcher: backup to SD card (MMC)
# Written by Lululla - 2026-11-21 - License: GPLv3
# BackupSuite launcher (MMC). Usage: backupmmc.sh <lang> <device_type> <media_path>
# All logic lives in common.sh; the right engine (backupsuite.sh or
# backupdmm.sh for Dreambox) is selected automatically.
. "$(dirname "$0")/common.sh"
launcher_main MMC "$@"

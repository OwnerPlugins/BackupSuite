# -*- coding: utf-8 -*-
"""
BackupSuite Plugin
FULL BACKUP UTILITY FOR ENIGMA2/OPENVISION
SUPPORTS VARIOUS MODELS

Original Developer: @persianpros
GitHub: https://github.com/persianpros/BackupSuite-PLi
SUPPORT FORUM: https://forums.openpli.org/

Modded by @Lululla (2025-06-15).
Modified by @Lululla (2026-11-21): restore screen fixed (Flash/About/Delete/
Unzip), safe shell quoting, multiboot detection, settings and automatic
backup, stop key, device detection, skins that follow the image skin.

The plugin lets the user pick a backup destination (USB, SD card, HDD or a
mounted network share), runs the matching launcher script in scripts/ and
can flash a previously made backup with ofgwrite.
"""
from os import listdir, statvfs, makedirs, getenv, access, W_OK
from os.path import basename, ismount, exists, isdir, isfile, join, realpath

try:
    from shlex import quote as shell_quote      # Python 3
except ImportError:
    from pipes import quote as shell_quote      # Python 2

from Components.ActionMap import ActionMap
from Components.FileList import FileList
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components.Harddisk import harddiskmanager

from Plugins.Plugin import PluginDescriptor
from enigma import (
    RT_HALIGN_LEFT,
    RT_VALIGN_CENTER,
    eListboxPythonMultiContent,
    gFont,
    getDesktop
)

from Screens.Console import Console
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import resolveFilename, SCOPE_PLUGINS

from . import _, __version__, LOGFILE, VERSIONFILE, ENIGMA2VERSIONFILE, OFGWRITE_BIN
# defines config.plugins.backupsuite (settings, schedule)
from . import scheduler


PLUGIN_DIR = resolveFilename(SCOPE_PLUGINS, "Extensions/BackupSuite")
SCRIPTS_DIR = join(PLUGIN_DIR, "scripts")
ICONS_DIR = join(PLUGIN_DIR, "img")
LOCALE_DIR = join(PLUGIN_DIR, "locale")
RETFILE = "/tmp/BackupSuite.ret"
BACKUP_LOGNAME = basename(LOGFILE)          # copied into every backup folder
NETWORK_FS = ("cifs", "nfs", "nfs4", "smbfs")

DEVICE_PROFILES = {
    "USB": {
        "icon": "usb.png",
        "script": "backupusb.sh",
        "desc": _("USB Storage")},
    "MMC": {
        "icon": "mmc.png",
        "script": "backupmmc.sh",
        "desc": _("SD Card")},
    "HDD": {
        "icon": "hdd.png",
                "script": "backuphdd.sh",
                "desc": _("Hard Disk")},
    "NET": {
        "icon": "network.png",
        "script": "backupnet.sh",
        "desc": _("Network Storage")},
    "RESTORE": {
        "icon": "restore.png",
        "script": "",
        "desc": _("Restore Backup")},
}

# Every file name ofgwrite may find in a backup folder
KNOWN_IMAGE_FILES = (
    "kernel_cfe_auto.bin", "rootfs.bin", "root_cfe_auto.jffs2",
    "root_cfe_auto.bin", "oe_kernel.bin", "oe_rootfs.bin", "kernel_auto.bin",
    "kernel.bin", "rootfs.tar.bz2", "uImage", "rootfs.ubi",
)

FORCE_MODE_MODELS = (
    "h9",
    "h9se",
    "h9combo",
    "h9combose",
    "i55plus",
    "i55se",
    "h10",
    "hzero",
    "h8",
)

EMMC_BZ2_MODELS = (
    "hd51", "h7", "sf4008", "sf5008", "sf8008", "sf8008m", "vs1500", "et11000",
    "et13000", "bre2ze4k", "spycat4k", "spycat4kmini", "protek4k", "e4hdultra",
    "arivacombo", "arivatwin", "dual",
)
EMMC_BZ2_PREFIXES = (
    "anadol", "axashis4", "dinobot4", "ferguson4", "mediabox4", "axashisc4",
)
HISI_UBI_MODELS = FORCE_MODE_MODELS + (
    "dinobotu55", "iziboxx3", "dinoboth265", "axashistwin", "protek4kx1",
)
HISI_BZ2_MODELS = (
    "hd60",
    "hd61",
    "multibox",
    "multiboxse",
    "multiboxplus",
    "pulse4k",
    "pulse4kmini",
)
OE_KERNEL_PREFIXES = (
    "fusion", "pure", "optimus", "force", "iqon", "ios", "tm2", "tmn", "tmt",
    "tms", "lunix", "mediabox", "vala",
)
ET_PREFIXES = ("et4", "et5", "et6", "et7", "et8", "et9", "et10")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def desktop_width():
    try:
        return getDesktop(0).size().width()
    except Exception:
        return 1280


def scale(value):
    """Scale a size designed for a 1280 wide (HD) desktop."""
    return int(value * desktop_width() / 1280.0)


def icon_path(name):
    path = join(ICONS_DIR, basename(name or ""))
    if name and isfile(path):
        return path
    return join(ICONS_DIR, "hdd.png")


def buttons_skin(y):
    """Four colour keys built from the plugin's own pictures."""
    out = []
    width = scale(1000)
    step = width // 4
    for i, color in enumerate(("red", "green", "yellow", "blue")):
        x = scale(20) + i * step
        out.append(
            '<ePixmap position="{0},{1}" size="{2},{2}" pixmap="{3}" alphatest="blend" />'
            '<widget source="key_{4}" render="Label" position="{5},{1}" size="{6},{2}" '
            'font="Regular;{7}" halign="left" valign="center" transparent="1" />'.format(
                x, y, scale(30), join(ICONS_DIR, color + ".png"), color,
                x + scale(40), step - scale(50), scale(20)))
    return "".join(out)


def get_box_type():
    try:
        from enigma import getBoxType
        return getBoxType().lower()
    except ImportError:
        try:
            from boxbranding import getBoxType
            return getBoxType().lower()
        except ImportError:
            return "unknown"


def is_dual_boot():
    if get_box_type() != "et8500":
        return False
    try:
        with open("/proc/mtd") as f:
            content = f.read()
        return "rootfs2" in content and "kernel2" in content
    except (IOError, OSError):
        return False


def requires_force_mode():
    return get_box_type() in FORCE_MODE_MODELS


def get_backup_files_pattern():
    """Regex of the backup file extensions for this receiver."""
    model = get_box_type()
    if model.startswith("dm"):
        if model.startswith("dm9") or model in (
                "dm520", "dm525", "dm7080", "dm820"):
            return r"\.(xz)$"
        return r"\.(nfi)$"
    if model.startswith("vu"):
        if "4k" in model:
            return r"\.(bin|bz2)$"
        return r"\.(bin|jffs2)$"
    if model in EMMC_BZ2_MODELS:
        return r"\.(bin|bz2)$"
    if model in FORCE_MODE_MODELS:
        return r"\.(ubi)$"
    if model in HISI_BZ2_MODELS:
        return r"\.(bz2)$"
    if model.startswith(ET_PREFIXES):
        return r"\.(bin)$"
    if model.startswith("ebox"):
        return r"\.(jffs2)$"
    if "4k" in model or "uhd" in model:
        return r"\.(bz2)$"
    return r"\.(zip|bin|bz2)$"


def expected_image_files(model):
    """Return the tuple of files ofgwrite needs for this receiver."""
    if model.startswith("dm"):                  # Dreambox
        if model.startswith("dm9"):
            return ("kernel.bin", "rootfs.tar.bz2")
        if model in ("dm520", "dm525", "dm7080", "dm820"):
            return ("*.xz",)
        return ("*.nfi",)
    if model.startswith("gb"):
        if "4k" in model:
            return ("kernel.bin", "rootfs.tar.bz2")
        return ("kernel.bin", "rootfs.bin")
    if model.startswith("vu"):
        if "4k" in model:
            return ("kernel_auto.bin", "rootfs.tar.bz2")
        if model in ("vuduo2", "vusolose", "vusolo2", "vuzero"):
            return ("kernel_cfe_auto.bin", "root_cfe_auto.bin")
        return ("kernel_cfe_auto.bin", "root_cfe_auto.jffs2")
    if model in EMMC_BZ2_MODELS or model.startswith(EMMC_BZ2_PREFIXES):
        return ("kernel.bin", "rootfs.tar.bz2")
    if model in HISI_UBI_MODELS:
        return ("uImage", "rootfs.ubi")
    if model in HISI_BZ2_MODELS:
        return ("uImage", "rootfs.tar.bz2")
    if model.startswith(ET_PREFIXES):
        return ("kernel.bin", "rootfs.bin")
    if model.startswith("ebox"):
        return ("kernel_cfe_auto.bin", "root_cfe_auto.jffs2")
    if model.startswith(OE_KERNEL_PREFIXES):
        return ("oe_kernel.bin", "oe_rootfs.bin")
    if "4k" in model or "uhd" in model:
        return ("oe_kernel.bin", "rootfs.tar.bz2")
    return ("kernel.bin", "rootfs.bin")


def get_mounted_network_shares():
    """Mounted network shares, read from /proc/mounts."""
    shares = []
    seen = set()
    try:
        with open("/proc/mounts", "r") as f:
            lines = f.readlines()
    except (IOError, OSError) as e:
        print("[BackupSuite] Error reading /proc/mounts: {0}".format(e))
        return shares

    for line in lines:
        parts = line.split()
        if len(parts) < 3 or parts[2].lower() not in NETWORK_FS:
            continue
        device, mountpoint, fstype = parts[0], parts[1].replace(
            "\\040", " "), parts[2]
        if mountpoint in seen:
            continue
        seen.add(mountpoint)
        try:
            st = statvfs(mountpoint)
            free_str = "{0:.2f} {1}".format(
                st.f_bavail *
                st.f_frsize /
                float(
                    1024 ** 3),
                _("GB"))
            total_str = "{0:.2f} {1}".format(
                st.f_blocks * st.f_frsize / float(1024 ** 3), _("GB"))
        except OSError:
            free_str = total_str = _("Unknown")
        server = device.split("/")[-1].split(":")[0] or basename(mountpoint)
        shares.append({
            "server": server,
            "mountpoint": mountpoint,
            "freespace": free_str,
            "totalspace": total_str,
            "fstype": fstype.upper(),
        })
    return shares


def block_device_name(device):
    """'/dev/sda1' -> 'sda', '/dev/mmcblk0p1' -> 'mmcblk0'."""
    name = basename(device or "")
    if name.startswith(("mmcblk", "nvme")):
        return name.split("p")[0] if "p" in name[4:] else name
    return name.rstrip("0123456789")


def device_type_from_sysfs(base):
    sysfs = "/sys/block/{0}".format(base)
    if not base or not exists(sysfs):
        return None
    if base.startswith("mmcblk"):
        return "MMC"
    if base.startswith("nvme"):
        return "HDD"
    try:
        path = realpath(join(sysfs, "device")).lower()
        if "/usb" in path:
            return "USB"
        if "/ata" in path or "sata" in path:
            return "HDD"
        with open(join(sysfs, "queue/rotational")) as f:
            if f.read().strip() == "1":
                return "HDD"
    except (IOError, OSError):
        pass
    return None


def get_device_type(device, description, mountpoint):
    """USB, MMC or HDD for a mounted partition."""
    # 1. The mount point name chosen by the image/user is the strongest hint
    mp = basename(mountpoint.rstrip("/")).lower()
    if mp in ("hdd", "hdd1", "hdd2", "harddisk", "sata", "nvme", "ssd"):
        return "HDD"
    if mp in ("mmc", "mmc1", "sdcard", "card", "microsd"):
        return "MMC"
    if mp.startswith("usb"):
        return "USB"
    # 2. Real hardware information
    hw = device_type_from_sysfs(block_device_name(device))
    if hw:
        return hw
    # 3. Whole words of the description
    words = set(
        description.lower().replace(
            "-",
            " ").replace(
            "(",
            " ").replace(
                ")",
            " ").split())
    if words & set(("mmc", "emmc", "sdcard", "card")):
        return "MMC"
    if words & set(("sata", "hdd", "nvme", "ssd", "harddisk")
                   ) or "hard disk" in description.lower():
        return "HDD"
    return "USB"


def get_available_backup_devices():
    """Mounted local partitions that can receive a backup."""
    devices = []
    seen = set()
    for p in harddiskmanager.getMountedPartitions():
        mountpoint = (getattr(p, "mountpoint", "") or "").rstrip("/") or "/"
        if mountpoint == "/" or mountpoint in seen or not ismount(mountpoint):
            continue
        fs_type = getattr(p, "filesystem", None)
        if callable(fs_type):
            try:
                fs_type = fs_type()
            except Exception:
                fs_type = None
        if fs_type and str(fs_type).lower() in NETWORK_FS:
            continue
        seen.add(mountpoint)
        device_type = get_device_type(
            getattr(p, "device", "") or "",
            getattr(p, "description", "") or "",
            mountpoint)
        profile = DEVICE_PROFILES[device_type]
        print("[BackupSuite] {0} -> {1}".format(mountpoint, device_type))
        devices.append({
            "type": device_type,
            "path": mountpoint,
            "desc": profile["desc"],
            "icon": icon_path(profile["icon"]),
            "script": join(SCRIPTS_DIR, profile["script"]),
        })
    return devices


def get_lang():
    """Two letter language code with a matching translation, else 'en'."""
    try:
        from Components.config import config
        lng = config.osd.language.value or getenv("LANG", "en_US")
    except Exception:
        lng = getenv("LANG", "en_US")
    base = lng.split(".")[0].split("_")[0][:2].lower()
    if base and isdir(join(LOCALE_DIR, base)):
        return base
    return "en"


# --------------------------------------------------------------------------
# Multiboot detection (same sources the openATV backup and ofgwrite use)
# --------------------------------------------------------------------------

CMDLINE_FILE = "/proc/cmdline"
KERNELDEV_FILE = "/sys/firmware/devicetree/base/chosen/kerneldev"
EXTERNAL_DISK_MAJORS = (
    8,
    65,
    66,
    67,
    68,
    69,
    70,
    71,
    128,
    129,
    130,
    131,
    132,
    133,
    134,
    135,
    259)


def read_first_line(path):
    try:
        with open(path, "r") as f:
            return f.readline().replace("\0", "").strip()
    except (IOError, OSError):
        return ""


def cmdline_params():
    params = {}
    try:
        with open(CMDLINE_FILE, "r") as f:
            for token in f.read().split():
                if "=" in token:
                    key, value = token.split("=", 1)
                    params[key] = value
    except (IOError, OSError):
        pass
    return params


def trailing_number(text):
    digits = ""
    for ch in reversed(text):
        if not ch.isdigit():
            break
        digits = ch + digits
    return digits


def folder_multiboot(root="/"):
    """'NeoBoot: <image>' / 'OpenMultiboot: <image>' when the running image
    was started by a folder multiboot, else ''."""
    name = read_first_line(join(root, ".multinfo"))
    if name or isfile(join(root, ".multinfo")):
        return "NeoBoot: {0}".format(name or "?")
    omb = join(root, "omb/open-multiboot")
    try:
        candidates = [f for f in listdir(
            omb) if f == ".selected" or f.endswith("-selected")]
    except OSError:
        candidates = []
    for f in candidates:
        name = read_first_line(join(omb, f))
        if name and name != "flash" and not name.endswith("-flash"):
            return "OpenMultiboot: {0}".format(name)
    return ""


def root_is_external():
    """True when / is on a USB/SATA/NVMe disk instead of the internal flash."""
    try:
        from os import stat, major
        return major(stat("/").st_dev) in EXTERNAL_DISK_MAJORS
    except Exception:
        return False


def get_multiboot_info():
    """Describe the running image: eMMC/NAND slot and folder multiboots."""
    params = cmdline_params()
    info = {
        "slot": "",
        "folder": folder_multiboot(),
        "external": root_is_external(),
        "kexec": params.get("kexec") == "1"}
    subdir = params.get("rootsubdir", "")
    kerneldev = read_first_line(KERNELDEV_FILE)
    root = params.get("root", "")
    if subdir:
        number = trailing_number(subdir)
        info["slot"] = _("Slot {0} ({1})").format(
            number, subdir) if number else subdir
    elif kerneldev.startswith("emmcflash0."):
        part = kerneldev.split(".", 1)[1]
        info["slot"] = _("Slot {0} ({1})").format(
            trailing_number(part) or "1", part)
    elif root.startswith("/dev/sd") and not info["folder"]:
        info["slot"] = _("Image on USB ({0})").format(root)
    return info


def multiboot_backup_note(info):
    if info["folder"]:
        return "\n\n" + _(
            "You are running an image started by {0}.\n"
            "The backup will contain THIS image with the kernel that is now in the flash. "
            "To back up the image in flash, boot the flash image first.").format(
            info["folder"])
    if info["external"] and not info["slot"]:
        return "\n\n" + _(
            "The running image is on an external device (multiboot such as Barry Allen).\n"
            "The backup will contain this image with the kernel that is now in the flash.")
    if info["slot"]:
        return "\n\n" + \
            _("Running image: {0}.\nThe backup will contain this image with its own kernel.").format(info["slot"])
    return ""


def multiboot_flash_note(info):
    if info["folder"] or (info["external"] and not info["slot"]):
        return "\n\n" + _(
            "WARNING: you are not running the image in the internal flash ({0}).\n"
            "Flashing will overwrite the INTERNAL FLASH image, not the image you are using now.").format(
            info["folder"] or _("external device"))
    if info["slot"]:
        return "\n\n" + _(
            "Multiboot: ofgwrite will write into the slot that is running now: {0}.\n"
            "To flash another slot, boot that slot first.").format(
            info["slot"])
    return ""


def write_enigma2_version():
    try:
        from Components.About import getEnigmaVersionString
        with open(ENIGMA2VERSIONFILE, "w") as f:
            f.write(getEnigmaVersionString())
    except Exception:
        pass


def is_safe_backup_dir(path):
    """True only for a real backup folder that may be deleted."""
    path = realpath(path.rstrip("/"))
    if not path.startswith("/media/") and not path.startswith("/hdd/"):
        return False
    if path.count("/") < 3 or ismount(path) or has_mounts_below(path):
        return False
    return isfile(join(path, VERSIONFILE))


def has_mounts_below(path):
    """True if a filesystem is mounted inside path: rm -rf would wipe it."""
    prefix = path.rstrip("/") + "/"
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) > 1 and parts[1].replace(
                        "\\040", " ").startswith(prefix):
                    return True
    except (IOError, OSError):
        return True     # unknown: be safe
    return False


# --------------------------------------------------------------------------
# Main screen
# --------------------------------------------------------------------------

LOCKDIR = "/tmp/.backupsuite.lock"


def backup_running():
    """True while a backup started by any launcher is running (see common.sh)."""
    try:
        with open(join(LOCKDIR, "pid")) as f:
            pid = int(f.read().strip())
        from os import kill
        kill(pid, 0)
        return True
    except Exception:
        return False


def backup_command(script_path, device_type, media_path, retfile=None):
    cmd = "sh {script} {lang} {dtype} {media}".format(
        script=shell_quote(script_path),
        lang=shell_quote(get_lang()),
        dtype=shell_quote(device_type),
        media=shell_quote(media_path))
    if retfile:
        # Console does not return the exit code: keep it in retfile
        cmd = "rm -f {ret}; {cmd}; echo $? > {ret}".format(
            ret=shell_quote(retfile), cmd=cmd)
    return cmd


def failure_message():
    """Short reason of the last failed backup, from the log."""
    error_msg = _("Backup failed! Check log: {0}").format(LOGFILE)
    try:
        with open(LOGFILE, "r") as f:
            log_content = f.read()
        if "No space left" in log_content:
            error_msg = _("Backup failed: Not enough free space on device!")
        elif "Permission denied" in log_content:
            error_msg = _("Backup failed: Write permission denied!")
        elif "Read-only file system" in log_content:
            error_msg = _("Backup failed: Device is read-only!")
        elif "Connection refused" in log_content or "Host is down" in log_content:
            error_msg = _("Backup failed: Network connection lost!")
        elif log_content.strip():
            last_lines = "\n".join(log_content.splitlines()[-5:])
            error_msg = _("Backup failed! Last errors:") + "\n" + last_lines
    except (IOError, OSError):
        pass
    return error_msg


def start_console_backup(
        session,
        device_type,
        media_path,
        script_path,
        callback=None):
    """Run a backup in a console the user can watch and stop."""
    if not media_path or not isdir(media_path):
        session.open(
            MessageBox,
            _("No device type selected"),
            MessageBox.TYPE_ERROR)
        return False
    if not script_path or not isfile(script_path):
        session.open(
            MessageBox,
            _("Backup script not found for {0}: {1}").format(
                device_type, basename(script_path) if script_path else "N/A"),
            MessageBox.TYPE_ERROR)
        return False
    if backup_running():
        session.open(
            MessageBox,
            _("Another backup is already running."),
            MessageBox.TYPE_ERROR)
        return False
    write_enigma2_version()
    cmd = backup_command(script_path, device_type, media_path, RETFILE)
    print("[BackupSuite] Executing: {0}".format(cmd))
    title = _("{0} Backup").format(device_type) + " - " + _("RED: stop")
    if callback:
        session.openWithCallback(callback, BackupConsole, title, [cmd])
    else:
        session.open(BackupConsole, title, [cmd])
    return True


class BackupConsole(Console):
    """Console with a RED key to stop a running backup.

    The backup scripts trap SIGINT: they unmount the read-only bind of /,
    remove their work folder and exit with an error."""

    def __init__(
            self,
            session,
            title="Console",
            cmdlist=None,
            finishedCallback=None,
            closeOnSuccess=False):
        Console.__init__(
            self,
            session,
            title,
            cmdlist,
            finishedCallback,
            closeOnSuccess)
        self.skinName = "Console"
        self.stopped = False
        self["BackupStopActions"] = ActionMap(
            ["ColorActions"], {"red": self.askStop}, -2)

    def isRunning(self):
        try:
            return self.run < len(self.cmdlist)
        except Exception:
            return False

    def askStop(self):
        if self.isRunning() and not self.stopped:
            self.session.openWithCallback(
                self.stopConfirmed,
                MessageBox,
                _("Do you really want to stop the backup?"),
                MessageBox.TYPE_YESNO,
                default=False)

    def stopConfirmed(self, answer):
        if answer and self.isRunning():
            self.stopped = True
            try:
                self.container.sendCtrlC()
            except Exception as e:
                print("[BackupSuite] sendCtrlC failed: {0}".format(e))


class BackupDeviceList(MenuList):
    """Device list that fits whatever skin is applied (embedded or the image's own)."""

    def __init__(self, list):
        MenuList.__init__(self, list, False, eListboxPythonMultiContent)
        self.item_height = scale(60)
        self.item_width = scale(1020)
        self.l.setFont(0, gFont("Regular", scale(26)))
        self.l.setItemHeight(self.item_height)

    def adaptToSkin(self):
        """Call after the skin is applied: a skin (e.g. OpenATV's own
        "BackupStart" screen) may set its own itemHeight, which would clip
        rows drawn for a different height. Re-apply ours and use the real
        width of the list."""
        try:
            width = self.instance.size().width()
            if width > 0:
                self.item_width = width
        except Exception:
            pass
        self.item_height = max(scale(60), 54)
        self.l.setItemHeight(self.item_height)
        self.l.setFont(0, gFont("Regular", int(self.item_height * 0.42)))


def BackupDeviceEntryComponent(entry, height=None, width=None):
    height = height or scale(60)
    width = width or scale(1020)
    icon_size = min(50, height - 4)
    text_x = scale(10) + icon_size + scale(20)
    icon = LoadPixmap(entry[1])
    return [
        entry,
        (getattr(eListboxPythonMultiContent, "TYPE_PIXMAP_ALPHABLEND",
                 eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST),
         scale(10), (height - icon_size) // 2, icon_size, icon_size, icon),
        (eListboxPythonMultiContent.TYPE_TEXT,
         text_x, 0, max(width - text_x - scale(10), 100), height,
         0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, entry[0]),
    ]


class BackupStart(Screen):
    def __init__(self, session, args=0):
        self.skin = (
            '<screen position="center,center" size="{0},{1}" title="Backup Suite">'
            '<widget name="devicelist" position="{2},{2}" size="{3},{4}" scrollbarMode="showOnDemand" />'
            '{5}</screen>'.format(
                scale(1040),
                scale(470),
                scale(10),
                scale(1020),
                scale(400),
                buttons_skin(
                    scale(425))))
        Screen.__init__(self, session)
        self.session = session
        self["key_red"] = StaticText(_("Close"))
        self["key_green"] = StaticText(_("Backup"))
        self["key_yellow"] = StaticText(_("Restore"))
        self["key_blue"] = StaticText(_("Help"))
        self.devicelist = []
        self["devicelist"] = BackupDeviceList([])
        self["actions"] = ActionMap(
            ["SetupActions", "ColorActions", "EPGSelectActions", "HelpActions"],
            {
                "red": self.close,
                "cancel": self.close,
                "green": self.deviceSelected,
                "ok": self.deviceSelected,
                "yellow": self.startRestore,
                "blue": self.show_help,
                "displayHelp": self.show_help,
                "info": self.keyInfo,
            }, -1)
        self["setupActions"] = ActionMap(
            ["MenuActions"], {"menu": self.openSetup}, -1)
        self.onLayoutFinish.append(self.layoutFinished)

    def layoutFinished(self):
        self.setTitle(_("Backup Suite v{0}").format(__version__))
        self["devicelist"].adaptToSkin()
        self.populateDeviceList()

    def populateDeviceList(self):
        self.devicelist = []
        for dev in get_available_backup_devices():
            label = "{0} ({1})".format(dev["desc"], basename(dev["path"]))
            self.devicelist.append(
                (_("Backup to {0}").format(label),
                 dev["icon"],
                    dev["type"],
                    dev["path"],
                    dev["script"]))

        if get_mounted_network_shares():
            net = DEVICE_PROFILES["NET"]
            self.devicelist.append(
                (_("Backup to Network"), icon_path(
                    net["icon"]), "NET", None, join(
                    SCRIPTS_DIR, net["script"])))

        restore = DEVICE_PROFILES["RESTORE"]
        self.devicelist.append(
            (_("Restore Backup"), icon_path(
                restore["icon"]), "RESTORE", None, ""))
        self.devicelist.append(
            (_("Settings and automatic backup"),
             icon_path("f_menu.png"),
             "SETUP",
             None,
             ""))

        lst = self["devicelist"]
        self["devicelist"].setList([BackupDeviceEntryComponent(
            e, lst.item_height, lst.item_width) for e in self.devicelist])

    def getSelectedEntry(self):
        selection = self["devicelist"].getCurrent()
        if isinstance(selection, list) and selection:
            selection = selection[0]
        if isinstance(selection, tuple) and len(selection) >= 5:
            return selection
        return None

    def deviceSelected(self):
        entry = self.getSelectedEntry()
        if not entry:
            return
        description, icon, dev_type, dev_path, script = entry
        if dev_type == "NET":
            self.start_net_backup()
        elif dev_type == "RESTORE":
            self.startRestore()
        elif dev_type == "SETUP":
            self.openSetup()
        elif dev_type in ("USB", "MMC", "HDD"):
            self.session.openWithCallback(
                lambda result: result and self.execute_backup(
                    dev_type,
                    dev_path,
                    script),
                MessageBox,
                _("Do you want to make a backup to {0}?\n\nThis may take several minutes.").format(
                    "{0} ({1})".format(
                        DEVICE_PROFILES[dev_type]["desc"],
                        dev_path)) +
                multiboot_backup_note(
                    get_multiboot_info()),
                MessageBox.TYPE_YESNO)

    def execute_backup(self, device_type, media_path, script_path):
        start_console_backup(
            self.session,
            device_type,
            media_path,
            script_path,
            self.console_closed)

    def start_net_backup(self):
        shares = get_mounted_network_shares()
        if not shares:
            self.session.open(
                MessageBox,
                _("No network shares mounted! Please mount a share first."),
                MessageBox.TYPE_ERROR)
            return
        menu = []
        for share in shares:
            text = "{0} ({1}) - {2}  {3} {4} / {5} {6}".format(
                share["server"], share["fstype"], share["mountpoint"],
                _("Free:"), share["freespace"], _("Total:"), share["totalspace"])
            menu.append((text, share["mountpoint"]))
        self.session.openWithCallback(
            self.net_share_selected, MessageBox,
            _("Select network share for backup:"), list=menu)

    def net_share_selected(self, selected_path):
        if not selected_path or selected_path is True:
            return
        backup_dir = join(selected_path, "backup")
        if not exists(backup_dir):
            try:
                makedirs(backup_dir)
            except OSError as e:
                self.session.open(
                    MessageBox, _("Could not create backup directory: {0}\nError: {1}").format(
                        backup_dir, e), MessageBox.TYPE_ERROR)
                return
        if not access(backup_dir, W_OK):
            self.session.open(
                MessageBox,
                _("No write permission for: {0}").format(backup_dir),
                MessageBox.TYPE_ERROR)
            return
        self.session.openWithCallback(
            lambda result: result and self.execute_backup(
                "NET", backup_dir, join(SCRIPTS_DIR, DEVICE_PROFILES["NET"]["script"])),
            MessageBox,
            _("Do you want to make a backup to {0}?\n\nThis may take several minutes.").format(backup_dir)
            + multiboot_backup_note(get_multiboot_info()),
            MessageBox.TYPE_YESNO)

    def openSetup(self):
        from .setup import BackupSuiteSetup
        self.session.open(BackupSuiteSetup)

    def startRestore(self):
        self.session.open(
            FlashImageConfig,
            "/media/",
            get_backup_files_pattern())

    def show_help(self):
        self.session.open(BackupHelpScreen)

    def keyInfo(self):
        self.session.open(WhatisNewInfo)

    def console_closed(self, *args):
        try:
            with open(RETFILE) as f:
                retval = int(f.read().strip() or "0")
        except (IOError, OSError, ValueError):
            retval = 0
        if retval != 0:
            self.session.open(
                MessageBox,
                failure_message(),
                MessageBox.TYPE_ERROR,
                timeout=30)


# --------------------------------------------------------------------------
# Restore / flash screen
# --------------------------------------------------------------------------

class FlashImageConfig(Screen):
    def __init__(self, session, curdir, matchingPattern=None):
        self.skin = (
            '<screen position="center,center" size="{0},{1}" title="Flash">'
            '<widget source="curdir" render="Label" position="{2},{2}" size="{3},{4}" '
            'font="Regular;{5}" valign="center" />'
            '<widget name="filelist" position="{2},{6}" size="{3},{7}" scrollbarMode="showOnDemand" />'
            '{8}</screen>'.format(
                scale(1040), scale(560), scale(10), scale(1020), scale(30), scale(22),
                scale(50), scale(450), buttons_skin(scale(515))))
        Screen.__init__(self, session)
        self.setTitle(_("Select the folder with backup"))
        self["key_red"] = StaticText(_("Close"))
        self["key_green"] = StaticText("")
        self["key_yellow"] = StaticText("")
        self["key_blue"] = StaticText("")
        self["curdir"] = StaticText(_("Current: {0}").format(curdir or ""))
        self.founds = False
        self.dualboot = is_dual_boot()
        self.ForceMode = requires_force_mode()
        # Actions currently bound to the colour keys
        self.green_action = None
        self.yellow_action = None
        self.blue_action = None

        if matchingPattern:
            extensions = matchingPattern.split("(")[-1].rstrip(")$")
            pattern = r"\.(" + extensions + "|zip)$"
        else:
            pattern = r"\.(zip)$"
        self.filelist = FileList(
            curdir,
            matchingPattern=pattern,
            enableWrapAround=True)
        self.filelist.onSelectionChanged.append(self.selectionChanged)
        self["filelist"] = self.filelist
        self["FilelistActions"] = ActionMap(
            ["SetupActions", "ColorActions"],
            {
                "green": self.keyGreen,
                "red": self.close,
                "yellow": self.keyYellow,
                "blue": self.keyBlue,
                "ok": self.keyOk,
                "cancel": self.close,
            })
        self.onLayoutFinish.append(self.selectionChanged)

    def get_selected_path(self):
        """Full path of the highlighted entry (folder or file)."""
        current_dir = self.filelist.getCurrentDirectory() or ""
        filename = self.filelist.getFilename()
        if not filename:
            return current_dir
        if self.filelist.canDescent():
            return filename                     # FileList gives full path for folders
        return join(current_dir, filename)

    def get_flash_dir(self):
        """Folder to flash: the highlighted folder, or the current one if a file is highlighted."""
        if self.filelist.canDescent():
            return self.get_selected_path()
        return self.filelist.getCurrentDirectory() or ""

    def selectionChanged(self):
        self.green_action = self.yellow_action = self.blue_action = None
        path = self.get_selected_path()
        self["curdir"].setText(_("Current: {0}").format(path))
        if not self.filelist.canDescent():
            if path.endswith(".zip"):
                self.yellow_action = "unzip"
            elif path:
                self.green_action = "flash"
        elif path and path != "/":
            self.green_action = "flash"
            if isfile(join(path, VERSIONFILE)):
                self.yellow_action = "info"
                if is_safe_backup_dir(path):
                    self.blue_action = "delete"
        self["key_green"].setText(_("Flash") if self.green_action else "")
        self["key_yellow"].setText(
            {"unzip": _("Unzip"), "info": _("About")}.get(self.yellow_action, ""))
        self["key_blue"].setText(_("Delete") if self.blue_action else "")

    def keyOk(self):
        if self.filelist.canDescent():
            self.filelist.descent()
            self.selectionChanged()

    # ---- flash -----------------------------------------------------------
    def keyGreen(self):
        if self.green_action != "flash" or not self.get_flash_dir():
            return
        message = _(
            "Warning!\nUse at your own risk! Make always a backup before use!\n"
            "Don't use it if you use multiple ubi volumes in ubi layer!") + "\n"
        if self.dualboot:
            message += _("\nYou are using dual multiboot!")
        message += multiboot_flash_note(get_multiboot_info())
        self.session.openWithCallback(
            self.confirmedWarning, MessageBox, message, MessageBox.TYPE_YESNO)

    def confirmedWarning(self, result):
        if result:
            self.showparameterlist()

    def showparameterlist(self):
        dirname = self.get_flash_dir()
        if not dirname:
            return
        model = get_box_type()
        backup_files = expected_image_files(model)
        no_backup_files = [
            f for f in KNOWN_IMAGE_FILES if f not in backup_files]

        text = _("Select parameter for start flash!\n")
        text += _("For flashing your receiver files are needed:\n")
        text += ", ".join(backup_files)
        text += _("\nThe found files:")
        self.founds = False
        try:
            names = listdir(dirname)
        except OSError:
            names = []
        for name in sorted(names):
            matches = name in backup_files or any(p.startswith(
                "*") and name.endswith(p[1:]) for p in backup_files)
            if matches:
                text += "\n" + _("  {0} (maybe ok)").format(name)
                self.founds = True
            elif name in no_backup_files:
                text += "\n" + _("  {0} (maybe error)").format(name)
                self.founds = True
        if not self.founds:
            text += _(" nothing!")

        if self.founds:
            choices = [
                (_("Simulate (no write)"), "simulate"),
                (_("Standard (root and kernel)"), "standard"),
                (_("Only root"), "root"),
                (_("Only kernel"), "kernel"),
            ]
            if self.dualboot:
                choices += [
                    (_("Simulate second partition (no write)"), "simulate2"),
                    (_("Second partition (root and kernel)"), "standard2"),
                    (_("Second partition (only root)"), "rootfs2"),
                    (_("Second partition (only kernel)"), "kernel2"),
                ]
        else:
            choices = [(_("Exit"), "exit")]
        self.session.openWithCallback(
            self.Callbackflashing, MessageBox, text, simple=True, list=choices)

    def Callbackflashing(self, ret):
        if not ret or ret is True:
            return
        if ret == "exit":
            self.close()
            return
        if self.session.nav.RecordTimer.isRecording():
            self.session.open(
                MessageBox,
                _("A recording is currently running. Please stop the recording before trying to start a flashing."),
                MessageBox.TYPE_ERROR)
            return

        options = {
            "simulate": (_("Simulate (no write)"), ["-n"], False),
            "standard": (_("Standard (root and kernel)"), (["-f"] if self.ForceMode else []) + ["-r", "-k"], True),
            "root": (_("Only root"), ["-r"], True),
            "kernel": (_("Only kernel"), ["-k"], True),
            "simulate2": (_("Simulate second partition (no write)"), ["-kmtd3", "-rmtd4", "-n"], False),
            "standard2": (_("Second partition (root and kernel)"), ["-kmtd3", "-rmtd4"], True),
            "rootfs2": (_("Second partition (only root)"), ["-rmtd4"], True),
            "kernel2": (_("Second partition (only kernel)"), ["-kmtd3"], True),
        }
        if ret not in options:
            return
        label, args, writes = options[ret]
        flash_dir = self.get_flash_dir()
        cmd = " ".join([shell_quote(OFGWRITE_BIN)] +
                       args + [shell_quote(flash_dir)])
        if writes:
            cmd += " > /dev/null 2>&1 &"

        if not self.founds:
            info = _("NOT found files for flashing!\n")
        elif not writes:
            info = _("Show only found image and mtd partitions.\n")
        else:
            info = (
                _("ofgwrite will stop enigma2 now to run the flash.\n") +
                _("Your STB will freeze during the flashing process.\n") +
                _("Please: DO NOT reboot your STB and turn off the power.\n") +
                _("The image or kernel will be flashing and auto booted in few minutes.\n"))
        message = "printf '%s\\n' " + shell_quote("\n" + info)
        self.session.open(Console, _("Flashing: ") + label, [message, cmd])

    # ---- unzip / info ----------------------------------------------------
    def keyYellow(self):
        if self.yellow_action == "unzip":
            filename = self.get_selected_path()
            self.session.openWithCallback(
                self.doUnzip,
                MessageBox,
                _("Do you really want to unpack {0} ?").format(
                    basename(filename)),
                MessageBox.TYPE_YESNO)
        elif self.yellow_action == "info":
            self.session.open(
                MessageBox,
                "\n\n\n{0}".format(
                    self.getBackupInfo()),
                MessageBox.TYPE_INFO)

    def getBackupInfo(self):
        try:
            with open(join(self.get_selected_path(), VERSIONFILE), "r") as f:
                return f.read()
        except (IOError, OSError):
            return ""

    def doUnzip(self, answer):
        if answer is not True:
            return
        zip_path = self.get_selected_path()
        target = self.filelist.getCurrentDirectory()
        if not zip_path or not target:
            return
        cmd = "unzip -o {0} -d {1}".format(
            shell_quote(zip_path), shell_quote(target))
        self.session.openWithCallback(self.refresh, Console, _("Unzip"), [cmd])

    def refresh(self, *args):
        self.filelist.refresh()
        self.selectionChanged()

    # ---- delete ----------------------------------------------------------
    def keyBlue(self):
        if self.blue_action == "delete":
            self.session.openWithCallback(
                self.confirmedDelete,
                MessageBox,
                _("You are about to delete this backup:\n\n{0}\nContinue?").format(
                    self.getBackupInfo()),
                MessageBox.TYPE_YESNO)

    def confirmedDelete(self, answer):
        if answer is not True:
            return
        backup_dir = self.get_selected_path().rstrip("/")
        if not is_safe_backup_dir(backup_dir):
            self.session.open(
                MessageBox,
                _("Error: invalid backup folder"),
                MessageBox.TYPE_ERROR)
            return
        cmds = [
            "printf '%s\\n' " + shell_quote("Removing backup:   " + basename(backup_dir)),
            "rm -rf {0}".format(shell_quote(realpath(backup_dir))),
        ]
        self.session.openWithCallback(
            self.refresh, Console, _("Delete backup"), cmds)


# --------------------------------------------------------------------------
# Help / what's new
# --------------------------------------------------------------------------

class BackupHelpScreen(Screen):
    def __init__(self, session):
        self.skin = (
            '<screen position="center,center" size="{0},{1}" title="BackupSuite Help">'
            '<widget name="help_text" position="{2},{2}" size="{3},{4}" font="Regular;{5}" />'
            '</screen>'.format(scale(900), scale(620), scale(15), scale(870), scale(590), scale(20)))
        Screen.__init__(self, session)
        self.setTitle(_("BackupSuite Help"))
        self["help_text"] = ScrollLabel()

        h = _("BackupSuite v{0}\n\n").format(__version__)
        h += _("Welcome to BackupSuite help.\n\n")
        h += _("Device List:\n")
        h += _("• Use UP/DOWN buttons to navigate through backup options\n")
        h += _("• Press OK to select an option\n\n")
        h += _("Backup Options:\n")
        h += _("• HDD Backup: Full system backup to internal hard drive\n")
        h += _("• USB Backup: Create a bootable USB recovery stick\n")
        h += _("• MMC Backup: Backup to external storage (eMMC)\n")
        h += _("• NET Backup: Backup to network storage (NAS/SMB)\n")
        h += _("• Restore: Flash a previously created backup or image\n\n")
        h += _("Button Functions:\n")
        h += _("• GREEN: Start backup for selected device\n")
        h += _("• YELLOW: Start restore process\n")
        h += _("• BLUE: Show this help screen\n")
        h += _("• RED: Close BackupSuite\n")
        h += _("• MENU: Settings and automatic backup\n\n")
        h += _("Automatic backup:\n")
        h += _("- Choose destination, time and days in the settings (MENU)\n")
        h += _("- It is postponed while a recording is running\n")
        h += _("- It can wake the receiver from deep standby and switch it off again\n")
        h += _("- Old backups can be deleted automatically (only BackupSuite backups)\n")
        h += _("- A file ending in .fbackup on a USB stick can start a backup to that stick\n\n")
        h += _("NET Backup Instructions:\n")
        h += _("1. Mount your network share first:\n")
        h += _("   - Go to Main Menu > Setup > System > Storage Manager\n")
        h += _("   - Select 'Network Storage' and add your NAS/SMB share\n")
        h += _("   - Enter server IP, share name, username and password\n")
        h += _("   - Mount the share and assign a name (e.g., NET_BACKUP)\n\n")
        h += _("2. Select 'NET Backup' from the device list\n")
        h += _("3. Choose your mounted network share\n")
        h += _("4. Confirm and start the backup process\n\n")
        h += _("Best Practices:\n")
        h += _("- Keep regular backups of your system\n")
        h += _("- Verify you have enough free storage space\n")
        h += _("- Never interrupt backup/restore processes\n")
        h += _("- Use quality USB drives for recovery sticks\n")
        h += _("- For network backups, use wired connection instead of Wi-Fi\n\n")
        h += _("Technical Notes:\n")
        h += _("- HDD and NET backups are kept in dated folders (fullbackup_<model>)\n")
        h += _("- USB and SD card backups are written ready for flashing in the root of the medium\n")
        h += _("- A USB stick containing a 'backupstick' file also receives an extra copy of HDD backups\n")
        h += _("- NET backups: Require mounted CIFS/NFS share with write permissions\n")
        h += _("- Restore: Works from HDD, USB, NET or MMC storage\n")
        h += _("- Always choose 'Standard (root and kernel)' when restoring\n\n")
        h += _("Troubleshooting NET Backup:\n")
        h += _("- Ensure NAS is powered on and accessible\n")
        h += _("- Verify username/password are correct\n")
        h += _("- Check share permissions (read/write)\n")
        h += _("- Test connection with ping command\n")
        h += _("- Use IP address instead of hostname if DNS fails\n\n")
        h += _("For detailed instructions and support:\n")
        h += _("Visit our GitHub repository:\n")
        h += "https://github.com/persianpros/BackupSuite-PLi\n"
        self["help_text"].setText(h)

        self["actions"] = ActionMap(
            ["DirectionActions", "SetupActions"],
            {
                "up": self["help_text"].pageUp,
                "down": self["help_text"].pageDown,
                "left": self["help_text"].pageUp,
                "right": self["help_text"].pageDown,
                "cancel": self.close,
                "ok": self.close,
            })


class WhatisNewInfo(Screen):
    def __init__(self, session):
        self.skin = (
            '<screen position="center,center" size="{0},{1}" title="What is new">'
            '<widget name="AboutScrollLabel" position="{2},{2}" size="{3},{4}" font="Regular;{5}" />'
            '</screen>'.format(scale(900), scale(560), scale(15), scale(870), scale(530), scale(20)))
        Screen.__init__(self, session)
        self.setTitle(_("What is new since the last release?"))
        self["AboutScrollLabel"] = ScrollLabel(_("Please wait"))
        self["actions"] = ActionMap(
            ["SetupActions", "DirectionActions"],
            {
                "cancel": self.close,
                "ok": self.close,
                "up": self["AboutScrollLabel"].pageUp,
                "down": self["AboutScrollLabel"].pageDown,
            })
        try:
            with open(join(PLUGIN_DIR, "whatsnew.txt")) as f:
                self["AboutScrollLabel"].setText(f.read())
        except (IOError, OSError):
            self["AboutScrollLabel"].setText(_("Change log not available"))


# --------------------------------------------------------------------------
# Plugin entry points
# --------------------------------------------------------------------------

def main(session, **kwargs):
    session.open(BackupStart)


def Plugins(path, **kwargs):
    description = "{0}, {1}".format(
        _("Backup and restore your image"), __version__)
    return [
        PluginDescriptor(
            name="BackupSuite",
            description=description,
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon="plugin.png",
            fnc=main),
        PluginDescriptor(
            name="BackupSuite",
            description=description,
            where=PluginDescriptor.WHERE_EXTENSIONSMENU,
            fnc=main),
        PluginDescriptor(
            name="BackupSuite",
            where=[
                PluginDescriptor.WHERE_AUTOSTART,
                PluginDescriptor.WHERE_SESSIONSTART],
            fnc=scheduler.autostart,
            wakeupfnc=scheduler.get_next_wakeup),
        PluginDescriptor(
            name="BackupSuite",
            where=PluginDescriptor.WHERE_FILESCAN,
            fnc=scheduler.start_filescan),
    ]

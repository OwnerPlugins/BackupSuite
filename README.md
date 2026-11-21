<h1 align="center">📦💾 BackupSuite for Enigma2</h1>

![Visitors](https://komarev.com/ghpvc/?username=Belfagor2005&label=Repository%20Views&color=blueviolet)
![Version](https://img.shields.io/badge/version-3.0--r12-blue.svg)
[![Enigma2](https://img.shields.io/badge/Enigma2-Plugin-ff6600.svg)](https://www.enigma2.net)
[![Python](https://img.shields.io/badge/Python-2.7%2B%20%7C%203.x-orange.svg)](https://www.python.org)
[![Build](https://github.com/Belfagor2005/BackupSuite/actions/workflows/pylint.yml/badge.svg)](https://github.com/Belfagor2005/BackupSuite/actions/workflows/pylint.yml)
[![Donate](https://img.shields.io/badge/_-Donate-red.svg?logo=githubsponsors&labelColor=555555&style=for-the-badge)](https://ko-fi.com/lululla)

<p align="center">
  <img src="https://github.com/Belfagor2005/BackupSuite/blob/main/usr/lib/enigma2/python/Plugins/Extensions/BackupSuite/plugin.png?raw=true" height="120">
</p>

Full image backup (kernel + root filesystem) of the running Enigma2 image, ready to be
flashed again with **ofgwrite** or from a USB stick. Supports about 270 receivers
(see `lookuptable.txt`), eMMC/NAND multiboot, network shares and scheduled backups.

## 📺 Screenshots

### **Main**
<p align="center">
  <img src="https://github.com/Belfagor2005/BackupSuite/blob/main/screen/00.png?raw=true" height="220">
</p>

### **On USB**
<p align="center">
  <img src="https://github.com/Belfagor2005/BackupSuite/blob/main/screen/11.png?raw=true" height="220">
  <img src="https://github.com/Belfagor2005/BackupSuite/blob/main/screen/22.png?raw=true" height="220">
</p>

### **On Net**
<p align="center">
  <img src="https://github.com/Belfagor2005/BackupSuite/blob/main/screen/33.png?raw=true" height="220">
</p>

### **On MMC**
<p align="center">
  <img src="https://github.com/Belfagor2005/BackupSuite/blob/main/screen/mmc1.png?raw=true" height="220">
  <img src="https://github.com/Belfagor2005/BackupSuite/blob/main/screen/mmc2.png?raw=true" height="220">
</p>

### **Info**
<p align="center">
  <img src="https://github.com/Belfagor2005/BackupSuite/blob/main/screen/info.png?raw=true" height="220">
</p>

### **Help**
<p align="center">
  <img src="https://github.com/Belfagor2005/BackupSuite/blob/main/screen/help.png?raw=true" height="220">
</p>

---

### **Device List**

* Use **UP/DOWN** to choose a destination, **OK** to start
* Only mounted devices are listed (USB, SD card, HDD, network shares)
* The last entries are **Restore Backup** and **Settings and automatic backup**

---

### **Backup Options**

* **HDD Backup**: full backup to the hard disk, kept in dated folders
* **USB Backup**: backup written ready for flashing in the root of the stick
* **MMC Backup**: the same on an SD card
* **NET Backup**: backup to a mounted network share (NAS/SMB/NFS)
* **Restore**: flash a backup or an image with ofgwrite

---

### **Button Functions**

* **GREEN / OK**: start the backup on the selected device
* **YELLOW**: restore (flash) a backup
* **BLUE**: help
* **MENU**: settings and automatic backup
* **INFO**: what's new
* **RED**: close BackupSuite
* **RED during a backup**: stop it (the scripts clean up after themselves)

---

### **Settings and Automatic Backup** (MENU)

* **Backup destination**: any mounted disk or network share
* **Automatic backup**: start time and days of the week, runs in the background
  * postponed (up to 3 hours) while a recording is running or about to start
  * optional: wake the receiver from deep standby for the backup, and switch it
    off again afterwards
  * message at the end with the result
* **Delete old backups automatically**: keep the newest N backups, or delete the
  ones older than 1 week … 6 months. Only BackupSuite backups are removed
  (`fullbackup_<model>/YYYYMMDD_HHMM` folders and `imagebackups/backup-*.zip`),
  never the newest one. The YELLOW key in the settings cleans up on request.
* **USB trigger**: a file ending in `.fbackup` on a USB stick offers a backup to
  that stick when it is plugged in

---

### **NET Backup Instructions**

1. **Mount your network share first**:
   * Go to **Main Menu > Setup > System > Storage Manager**
   * Select **"Network Storage"** and add your NAS/SMB share
   * Enter server IP, share name, username and password
   * Mount the share and assign a name (e.g., `NET_BACKUP`)
2. **Select "Backup to Network"** from the device list
3. **Choose** your mounted network share (the backup goes to `<share>/backup`)
4. **Confirm** and start the backup

---

### **Restore**

1. Select **Restore Backup** (or press YELLOW)
2. Browse to the backup folder, e.g. `/media/hdd/fullbackup_<model>/<date>/`,
   or to a zip in `imagebackups/` and press **YELLOW (Unzip)** first
3. Select the folder that contains the image files and press **GREEN (Flash)**
4. Choose **Standard (root and kernel)** for a full restore, or **Simulate** to
   only check the files
5. On multiboot receivers ofgwrite writes the slot that is running now: boot the
   slot you want to restore first

---

### **Multiboot**

* The backup always contains the **running** image with **its own kernel**:
  eMMC slots (`kernel=`/`rootsubdir`), Vu+ 4K kexec multiboot (`/zImage`),
  Broadcom `kerneldev` (hd51 and similar), NAND HiSilicon multiboot
* The slot is written in the `imageversion` file of the backup
* Images started by **NeoBoot**, **OpenMultiboot**, Barry Allen or from a USB disk
  are detected: the plugin explains what the backup will contain and warns that
  flashing writes the internal flash, not the image in use

---

### **Best Practices**

* Keep regular backups of your system (use the automatic backup)
* Verify you have enough free storage space
* Never switch off the receiver during a restore
* Use quality USB drives for recovery sticks
* For network backups, use a wired connection instead of Wi-Fi

---

### **Technical Notes**

* **HDD / NET backups**: `<destination>/fullbackup_<model>/<YYYYMMDD_HHMM>/<model folder>/`
* **USB / SD card backups**: `<stick>/<model folder>/` (ready to flash) plus a dated copy
* **Zip copy**: `<destination>/imagebackups/backup-<image>-<model>-<date>.zip`
  (the zip keeps the model folder, unzip it in the root of a stick to flash it)
* A USB stick with a file named `backupstick` also receives an extra copy of HDD backups
* Progress is shown during the backup (percent, elapsed and remaining time)
* Only one backup runs at a time; the root filesystem is read through a
  read-only bind mount, and nothing is ever deleted through a mount point
* Log of the last backup: `/tmp/BackupSuite.log` (also copied into the backup)
* Requirements (installed by opkg): `bzip2`, `mtd-utils`, `mtd-utils-ubifs`,
  `ofgwrite`; recommended: `zip`. The plugin uses the tools of the image, it
  does not ship its own binaries.
* Custom receiver table: put your own `lookuptable.txt` in `/etc`

---

### **Troubleshooting NET Backup**

* Ensure NAS is powered on and accessible
* Verify username/password are correct
* Check share permissions (read/write)
* Test connection with `ping` command
* Use IP address instead of hostname if DNS fails

---

### **What's new in 3.0-r12**

* Fixed: on 39 receivers a broken `lookuptable.txt` made the backup delete the
  whole destination drive
* Fixed: backups could not start (missing `message.py`)
* Multiboot: kernel of the running slot instead of always slot 1
* Settings screen, scheduled backups, automatic cleanup, USB trigger
* Progress with remaining time, stop button, clean zip names
* Safer package scripts (no Enigma2 restart while opkg is running)

Full list: `whatsnew.txt`

---

### **Credits**

* Original BackupSuite: **Pedro_Newbie**, **Persian Prince** (persianpros) and the
  OpenPLi / Open Vision teams
* Dreambox backup: **athoik**, **gutemine** (Barry Allen)
* Ideas for the automatic backup: **Dimitrij** (Automatic Full Backup)
* Plugin rewrite and maintenance: **Lululla**

Support: [OpenPLi forum](https://forums.openpli.org/) ·
Original project: [persianpros/BackupSuite-PLi](https://github.com/persianpros/BackupSuite-PLi)

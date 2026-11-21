#!/bin/sh

###############################################################################
#          BACKUP SUITE - FULL BACKUP ENGINE FOR DREAMBOX RECEIVERS           #
#                https://github.com/persianpros/BackupSuite-PLi               #
#                                                                             #
#     FULL BACKUP UTILITY FOR ENIGMA2/OPENVISION, SUPPORTS VARIOUS MODELS     #
#                   MAKES A FULL BACKUP READY FOR FLASHING.                   #
#               SUPPORT FORUM: https://forums.openpli.org/                    #
#                                                                             #
#                       UPDATE 20250615 BY LULULLA                            #
#                 MODIFIED 2026-11-21 BY LULULLA (3.0-r12)                    #
###############################################################################

### NOTES FOR BACKUP SUITE (LULULLA)
# **GOAL:** Backup script style unification
# **COLORS:**
# TITLE BLOCK (PURPLE)
# SYSTEM DETECTION (BLUE)
# INITIALIZATION (BLUE)
# ERROR HANDLING (RED)
# DEVICE DETECTION (BLUE)
# DEVICE INFORMATION (PURPLE)
# BACKUP SIZE ESTIMATION (GREEN)
# SIZE WARNING (YELLOW/RED)
# SEPARED LINE (YELLOW)
# PREPARING WORK ENVIRONMENT (BLUE)
# BACKUP START (GREEN)
# KERNEL BACKUP (BLUE)
# ROOT FILESYSTEM BACKUP (GREEN)
# FINALIZING BACKUP (BLUE)
# ZIP ARCHIVE CREATION (GREEN)
# EXTRA COPY TO USB (GREEN)
# CLEANUP AND STATISTICS (GREEN)
# PACKAGE LIST (WHITE)
# FINAL LOG COPY (WHITE)
# SUCCESS MESSAGE (GREEN)

## TESTING IF PROGRAM IS RUN FROM COMMANDLINE OR CONSOLE, JUST FOR THE COLORS ##

if tty > /dev/null ; then    # Commandline
    RED='\e[00;31m'    # Errors/failures
    GREEN='\e[00;32m'  # Success/positive messages
    YELLOW='\e[01;33m' # Warnings/important info
    BLUE='\e[01;34m'   # Phase headers
    PURPLE='\e[01;31m' # Titles/model info
    WHITE='\e[00;37m'  # Normal text
else                     # On the STB
    RED='\c00??0000'
    GREEN='\c0000??00'
    YELLOW='\c00????00'
    BLUE='\c0000????'
    PURPLE='\c00?:55>7'
    WHITE='\c00??????'
fi

# ========================= TITLE BLOCK (PURPLE) =============================
LINE="------------------------------------------------------------"
echo -n "$YELLOW"
echo "$LINE"
echo -n "$PURPLE"
echo "***   BACKUPSUITE PLUGIN FOR ENIGMA2/OPENVISION    ***"
echo "*** https://github.com/persianpros/BackupSuite-PLi ***"
echo -n "$YELLOW"
# echo "$LINE"
# echo -n "$WHITE"

# ==================== SYSTEM DETECTION (BLUE) ==============================
# echo -n "$YELLOW"
# echo "$LINE"
echo -n "$BLUE"

# Robust Python detection
PYTHON=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python2 >/dev/null 2>&1; then
    PYTHON="python2"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "Unable to find Python!" >&2
    exit 1
fi

# Get Python version
PYVERSION=$($PYTHON -V 2>&1 | awk '{print $2}')
case "$PYVERSION" in
    2.*) PYEXT="pyo" ;;
    3.*) PYEXT="pyc" ;;
    *)   echo "Unsupported Python version: $PYVERSION" >&2; exit 1 ;;
esac

# Portable directory listing options
LS_PORTABLE() {
    if ls -1 /tmp >/dev/null 2>&1; then
        ls -1 "$@"
    else
        ls -lSr "$@" | awk '{print $NF}'
    fi
}

# Robust file size calculation
get_file_size() {
    local file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -c %s "$file"
    elif command -v du >/dev/null 2>&1; then
        du -b "$file" | awk '{print $1}'
    else
        echo "0"
    fi
}

if [ -d "/usr/lib64/enigma2/python/Plugins/Extensions/BackupSuite" ]; then
    LIBDIR="/usr/lib64"
else
    LIBDIR="/usr/lib"
fi

# Usage: backupdmm.sh <media_path> [device_type] [lang]
MEDIA="${1%/}"
DEVICE_TYPE="$2"
LANG_CODE="${3:-${LANG:-en}}"
if [ -z "$SHOW" ] ; then
    if [ -f "$LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/message.py" ] ; then
        SHOW="$PYTHON $LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/message.py $LANG_CODE"
    else
        SHOW="echo"
    fi
fi
export SHOW
# multiboot helpers: kernel of the running slot, folder multiboots
. "$LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/scripts/multiboot.sh"

case "$DEVICE_TYPE" in
    HDD|NET) HARDDISK=1 ;;
    USB|MMC) HARDDISK=0 ;;
    *)       HARDDISK="${HARDDISK:-0}" ;;
esac
export HARDDISK

case "$MEDIA" in
    ""|/|/media|/tmp|/tmp/*)
        echo "Invalid backup destination: $MEDIA" >&2
        exit 1 ;;
esac
[ -d "$MEDIA" ] || { echo "Directory does not exist: $MEDIA" >&2 ; exit 1 ; }

echo -n $YELLOW



###################### FIRST DEFINE SOME PROGRAM BLOCKS #######################
############################# START LOGGING ###################################
log()
{
echo "$*" >> $LOGFILE
}

########################## DEFINE CLEAN-UP ROUTINE ############################
clean_up()
{
mb_unmount_all /tmp/bi/root
rmdir /tmp/bi/root > /dev/null 2>&1
rmdir /tmp/bi > /dev/null 2>&1
mb_safe_rmtree "$WORKDIR" > /dev/null 2>&1
}
trap 'mb_stop_bg; clean_up; exit 1' INT TERM HUP

###################### BIG OOPS!, HOLY SH... (SHELL SCRIPT :-))################
big_fail()
{
if [ -d $WORKDIR ] ; then
    log "FAIL!"
    log "Content so far of the working directory $WORKDIR "
    LS_PORTABLE $WORKDIR >> $LOGFILE
fi
clean_up
echo $RED
$SHOW "message15" 2>&1 | tee -a $LOGFILE # Image creation FAILED!
echo $WHITE
exit 1
}

######################## SAFE REMOVAL OF A BACKUP FOLDER #######################
safe_rm()
{
p="${1%/}"
unsafe=0
case "$p" in
    ""|/|*/..|*/../*|/media) unsafe=1 ;;
esac
[ "$(echo "$p" | tr -cd '/' | wc -c)" -lt 2 ] && unsafe=1
[ "$p" = "$MEDIA" ] && unsafe=1
[ -n "$TARGET" ] && [ "$p" = "${TARGET%/}" ] && unsafe=1
awk -v p="$p" '$2 == p { f = 1 } END { exit !f }' /proc/mounts && unsafe=1
mb_has_mounts_below "$p" && unsafe=1
if [ "$unsafe" = 1 ] ; then
    { $SHOW "message58" ; echo " $1" ; } 2>&1 | tee -a $LOGFILE
    big_fail
fi
rm -rf "$p"
}

############################ DEFINE IMAGE_VERSION #############################
image_version()
{
echo "Back-up = $BACKUPDATE"
echo "Version = $IMVER"
echo "Flashed = $FLASHED"
echo "Updated = $LASTUPDATE"
echo -n "Drivers = "
opkg list-installed | grep dvb-modules
echo "Enigma2 = $ENIGMA2DATE"
mb_describe
echo
echo $LINE
}

#################### CLEAN UP AND MAKE DESTINATION FOLDERS ####################
make_folders()
{
safe_rm "$MAINDEST"
log "Removed directory  = $MAINDEST"
mkdir -p "$MAINDEST"
log "Created directory  = $MAINDEST"
}

################ CHECK FOR THE NEEDED BINARIES IF THEY EXIST ##################
checkbinary()
{
if [ ! -f "$1" ] ; then {
    echo -n "$1 " ; $SHOW "message05"
    } 2>&1 | tee -a $LOGFILE
    big_fail
elif [ ! -x "$1" ] ; then
    {
    echo "Error: $1 " ; $SHOW "message35"
    } 2>&1 | tee -a $LOGFILE
    big_fail
fi
}

################### BACK-UP MADE AND REPORTING SIZE ETC. ######################
backup_made()
{
{
echo $LINE
$SHOW "message10" ; echo "$MAINDEST"     # USB Image created in:
$SHOW "message23"        # "The content of the folder is:"
LS_PORTABLE "$MAINDEST"
echo $LINE
if  [ "$HARDDISK" != 1 ]; then
    $SHOW "message11" ; echo "$EXTRA"        # and there is made an extra copy in:
    echo $LINE
fi
} 2>&1 | tee -a $LOGFILE
}

################### BACK-UP MADE AND REPORTING SIZE ETC. ######################
backup_made_nfi()
{
{
echo $LINE
$SHOW "message42" ; echo "$MAINDEST"     # NFI Image created in:
$SHOW "message23"        # "The content of the folder is:"
LS_PORTABLE "$MAINDEST"
echo $LINE
if  [ "$HARDDISK" != 1 ]; then
    $SHOW "message11" ; echo "$EXTRA"        # and there is made an extra copy in:
    echo $LINE
fi
} 2>&1 | tee -a $LOGFILE
}

############################## END PROGRAM BLOCKS #############################
########################## DECLARATION OF VARIABLES ###########################
BACKUPDATE=$(date +%Y.%m.%d_%H:%M)
DATE=$(date +%Y%m%d_%H%M)
if [ -f "$LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/speed.txt" ] ; then
    ESTSPEED=$(cat $LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/speed.txt)
    if [ $ESTSPEED -lt 50 ] ; then
        ESTSPEED="250"
    fi
else
    ESTSPEED="250"
fi
FLASHED=$(date -r /etc/version +%Y.%m.%d_%H:%M)
IMVER="$(mb_image_label)"
LASTUPDATE=$(date -r /var/lib/opkg/status +%Y.%m.%d_%H:%M)
ENIGMA2DATE=$(cat /tmp/enigma2version)
LOGFILE=/tmp/BackupSuite.log
MKFS="$(mb_tool mkfs.ubifs)"
MKFSJFFS2="$(mb_tool mkfs.jffs2)"
BUILDIMAGE="$(mb_tool buildimage)"
MTDPLACE=$(cat /proc/mtd | grep -w "kernel" | cut -d ":" -f 1)
NANDDUMP="$(mb_tool nanddump)"
START=$(date +%s)
if [ -f "/etc/lookuptable.txt" ] ; then
    LOOKUP="/etc/lookuptable.txt"
    $SHOW "message36"
else
    LOOKUP="$LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/lookuptable.txt"
fi
TARGET="XX"
UBINIZE="$(mb_tool ubinize)"
USEDsizebytes=$(df -B 1 /usr/ | grep [0-9]% | tr -s " " | cut -d " " -f 3)
USEDsizekb=$(df -k /usr/ | grep [0-9]% | tr -s " " | cut -d " " -f 3)
if [ -f "/var/lib/opkg/info/enigma2-plugin-extensions-backupsuite.control" ] ; then
    VERSION="Version: "$(cat /var/lib/opkg/info/enigma2-plugin-extensions-backupsuite.control | grep "Version: " | cut -d "+" -f 2)
else
    VERSION=$($SHOW "message37")
fi
WORKDIR="$MEDIA/.backupsuite_work"   # own name: never a folder of the user

######################### START THE LOGFILE $LOGFILE ##########################
echo -n "" > $LOGFILE
log "*** THIS BACKUP IS CREATED WITH THE BACKUPSUITE PLUGIN ***"
log "*****  https://github.com/OpenVisionE2/BackupSuite  ******"
log $LINE
log "Plugin version     = "$(cat /var/lib/opkg/info/enigma2-plugin-extensions-backupsuite.control | grep "Version: " | cut -d "+" -f 2- | cut -d "-" -f1)
log "Back-up media      = $MEDIA"
df -h "$MEDIA"  >> $LOGFILE
log $LINE
image_version >> $LOGFILE
log "Working directory  = $WORKDIR"

###### TESTING IF ALL THE BINARIES FOR THE BUILDING PROCESS ARE PRESENT #######
echo $RED
checkbinary $NANDDUMP
checkbinary $MKFS
checkbinary $UBINIZE
echo -n $WHITE

#############################################################################
# TEST IF RECEIVER IS SUPPORTED AND READ THE VARIABLES FROM THE LOOKUPTABLE #
IS_DREAMBOX=0
for f in /etc/modules-load.d/*dreambox-dvb-modules-dm*.conf ; do
    [ -e "$f" ] && IS_DREAMBOX=1
done
if [ "$IS_DREAMBOX" = 1 ] ; then
    if [ -f /etc/openvision/model ] ; then
        log "Open Vision detected"
        SEARCH=$(cat /etc/openvision/model | tr "A-Z" "a-z" | tr -d '[:space:]')
    else
        log "Non-Open Vision image detected"
        SEARCH=$(cat /proc/stb/info/model | tr "A-Z" "a-z" | tr -d '[:space:]')
    fi
else
    log "Not a dreambox! Exiting..."
    exit 1
fi

if [ -z "$SEARCH" ] ; then
    $SHOW "message01" 2>&1 | tee -a $LOGFILE   # No supported receiver found!
    exit 1
fi

############################## DM9X0 Situation ##############################
dm9x0_situation()
{
log "Found dm9x0, bz2 mode"
ROW="$(awk -F'\t' -v m="$SEARCH" 'NR > 1 && $2 == m { print; exit }' "$LOOKUP")"
col() { printf '%s\n' "$ROW" | cut -f "$1" ; }
MODEL="$(col 2)"
SHOWNAME="$(col 3)"
FOLDER="$(col 4)"
EXTR1="$(col 5)/$DATE"
EXTR2="$(col 6)"
case "$FOLDER" in
    /?*) ;;
    *) log "No valid lookuptable entry for $SEARCH"
       $SHOW "message01" 2>&1 | tee -a $LOGFILE
       big_fail ;;
esac
EXTRA="$MEDIA$EXTR1$EXTR2"
if  [ "$HARDDISK" = 1 ]; then
    MAINDEST="$MEDIA$EXTR1$FOLDER"
else
    MAINDEST="$MEDIA$FOLDER"
fi
MKUBIFS_ARGS="$(col 7)"
UBINIZE_ARGS="$(col 8)"
ROOTNAME="$(col 9)"
KERNELNAME="$(col 10)"
ACTION="$(col 11)"
MKFS="$(mb_tool tar)"
checkbinary $MKFS
if ! mb_tool bzip2 > /dev/null ; then
    echo -n "bzip2 " ; $SHOW "message38"
fi
BZIP2="$(mb_need_tool bzip2 bzip2)"
checkbinary $BZIP2
log "Destination        = $MAINDEST"
log $LINE

############# START TO SHOW SOME INFORMATION ABOUT BRAND & MODEL ##############
echo -n $PURPLE
echo -n "$SHOWNAME " | tr  a-z A-Z        # Shows the receiver brand and model
$SHOW "message02"              # BACK-UP TOOL FOR MAKING A COMPLETE BACK-UP
echo $BLUE
log "RECEIVER = $SHOWNAME "
log "MKUBIFS_ARGS = $MKUBIFS_ARGS"
log "UBINIZE_ARGS = $UBINIZE_ARGS"
echo "$VERSION"
echo $WHITE

############ CALCULATE SIZE, ESTIMATED SPEED AND SHOW IT ON SCREEN ############
$SHOW "message06"     #"Some information about the task:"
KERNELHEX=800000 # Not the real size (will be added later)
KERNEL=$((0x$KERNELHEX))           # Total Kernel size in bytes
TOTAL=$(($USEDsizebytes+$KERNEL))  # Total ROOTFS + Kernel size in bytes
KILOBYTES=$(($TOTAL/1024))         # Total ROOTFS + Kernel size in KB
MEGABYTES=$(($KILOBYTES/1024))
{
echo -n "KERNEL" ; $SHOW "message04" ; printf '%6s' $(($KERNEL/1024)); echo ' KB'
echo -n "ROOTFS" ; $SHOW "message04" ; printf '%6s' $USEDsizekb; echo ' KB'
echo -n "=TOTAL" ; $SHOW "message04" ; printf '%6s' $KILOBYTES; echo " KB (= $MEGABYTES MB)"
} 2>&1 | tee -a $LOGFILE
ESTTIMESEC=$(($KILOBYTES/($ESTSPEED*3)))
ESTMINUTES=$(( $ESTTIMESEC/60 ))
ESTSECONDS=$(( $ESTTIMESEC-(( 60*$ESTMINUTES ))))
echo $LINE
{
$SHOW "message03"  ; printf "%d.%02d " $ESTMINUTES $ESTSECONDS ; $SHOW "message25" # estimated time in minutes
echo $LINE
} 2>&1 | tee -a $LOGFILE

##################### PREPARING THE BUILDING ENVIRONMENT ######################
log "*** FIRST SOME HOUSEKEEPING ***"
mb_safe_rmtree "$WORKDIR" || big_fail       # GETTING RID OF THE OLD REMAINS IF ANY
log "Remove directory   = $WORKDIR"
mkdir -p "$WORKDIR"     # MAKING THE WORKING FOLDER WHERE EVERYTHING HAPPENS
log "Recreate directory = $WORKDIR"
mkdir -p /tmp/bi/root # this is where the complete content will be available
log "Create directory   = /tmp/bi/root"
sync
mb_bind_root /tmp/bi/root || big_fail   # read-only bind of the complete root
# Samba runtime sockets are not files: never back them up and never touch
# them on the live system (/tmp/bi/root is a bind mount of /)
TAR_EXCLUDES="--exclude=./var/lib/samba/msg.sock --exclude=./var/lib/samba/private/msg.sock --exclude=./var/nmbd"
# busybox tar may be built without --exclude: then just skip the excludes
"$(mb_tool tar)" --help 2>&1 | grep -q -- "--exclude" || TAR_EXCLUDES=""

############################## MAKING KERNELDUMP ##############################
log $LINE
$SHOW "message07" 2>&1 | tee -a $LOGFILE            # Create: kerneldump
if mb_dump_running_kernel "$WORKDIR/$KERNELNAME" "$PYTHON $LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/findkerneldevice.py" ; then
    log "Kernel of the running image taken from $MB_KERNEL_SOURCE"
elif [ "$SEARCH" = "dm900" -o "$SEARCH" = "dm920" ] ; then
    dd if=/dev/mmcblk0p1 of=$WORKDIR/$KERNELNAME
    log "Kernel resides on /dev/mmcblk0p1"
else
    $PYTHON $LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/findkerneldevice.py
    KERNEL=$(cat /sys/firmware/devicetree/base/chosen/kerneldev)
    log "Kernel device from devicetree: $(printf '%s' "$KERNEL" | tr -d '\000')"
    dd if=/dev/kernel of=$WORKDIR/$KERNELNAME > /dev/null 2>&1
fi

#############################  MAKING ROOT.UBI(FS) ############################
#############################  MAKING ROOT.UBI(FS) ############################
$SHOW "message06a" 2>&1 | tee -a $LOGFILE       #Create: root.ubifs
log $LINE

# Check if this is eMMC device (Ustym 4K Pro)
if [ -b "/dev/mmcblk0p16" ] && [ -b "/dev/mmcblk0p12" ]; then
    echo "eMMC device detected - using direct tar from mounted rootfs"
    
    # Mount rootfs partition and create tar directly
    mkdir -p /tmp/rootfs_mount
    if mount -o ro /dev/mmcblk0p16 /tmp/rootfs_mount; then
        $MKFS -cf "$WORKDIR/rootfs.tar" -C /tmp/rootfs_mount $TAR_EXCLUDES .
        # rmdir only: if umount failed, rm -rf would wipe the mounted rootfs
        umount /tmp/rootfs_mount && rmdir /tmp/rootfs_mount
        echo "RootFS tar created directly from eMMC partition"
    else
        echo "ERROR: Cannot mount rootfs partition, using standard method"
        $MKFS -cf "$WORKDIR/rootfs.tar" -C /tmp/bi/root $TAR_EXCLUDES .
    fi
else
    # Standard method for other devices
    $MKFS -cf "$WORKDIR/rootfs.tar" -C /tmp/bi/root $TAR_EXCLUDES .
fi

$BZIP2 $WORKDIR/rootfs.tar

############################ ASSEMBLING THE IMAGE #############################
make_folders
mv "$WORKDIR/$ROOTNAME" "$MAINDEST/$ROOTNAME"
mv "$WORKDIR/$KERNELNAME" "$MAINDEST/$KERNELNAME"
image_version > "$MAINDEST/imageversion"
if  [ "$HARDDISK" != 1 ]; then
    mkdir -p "$EXTRA"
    log "Created directory  = $EXTRA"
    cp -r "$MAINDEST" "$EXTRA"   #copy the made back-up to images
fi
if [ -f "$MAINDEST/$ROOTNAME" -a -f "$MAINDEST/$KERNELNAME" ] ; then
        backup_made
        $SHOW "message14"            # Instructions on how to restore the image.
        echo $LINE
else
    big_fail
fi

#################### CHECKING FOR AN EXTRA BACKUP STORAGE #####################
if  [ "$HARDDISK" = 1 ]; then                     # looking for a valid usb-stick
    for candidate in $(cut -d ' ' -f 2 /proc/mounts | grep '^/media/')
    do
        [ "$candidate" = "$MEDIA" ] && continue
        for marker in "${candidate}/"*[Bb][Aa][Cc][Kk][Uu][Pp][Ss][Tt][Ii][Cc][Kk]* ; do
            [ -e "$marker" ] && TARGET="${candidate}"
        done
    done
    if [ "$TARGET" != "XX" ] ; then
        echo -n $GREEN
        $SHOW "message17" 2>&1 | tee -a $LOGFILE    # Valid USB-flashdrive detected, making an extra copy
        echo $LINE
        TOTALSIZE="$(df -h "$TARGET" | tail -n 1 | awk {'print $2'})"
        FREESIZE="$(df -h "$TARGET" | tail -n 1 | awk {'print $4'})"
        {
        $SHOW "message09" ; echo -n "$TARGET ($TOTALSIZE, " ; $SHOW "message16" ; echo "$FREESIZE)"
        } 2>&1 | tee -a $LOGFILE
        safe_rm "$TARGET$FOLDER"
        mkdir -p "$TARGET$FOLDER"
        cp -r "$MAINDEST/." "$TARGET$FOLDER"
        echo $LINE >> $LOGFILE
        echo "MADE AN EXTRA COPY IN: $TARGET" >> $LOGFILE
        df -h "$TARGET"  >> $LOGFILE
        $SHOW "message19" 2>&1 | tee -a $LOGFILE    # Backup finished and copied to your USB-flashdrive
    else
        $SHOW "message40" >> $LOGFILE
    fi
sync
fi

################## CLEANING UP AND REPORTING SOME STATISTICS ##################
clean_up
END=$(date +%s)
DIFF=$(( $END - $START ))
MINUTES=$(( $DIFF/60 ))
SECONDS=$(( $DIFF-(( 60*$MINUTES ))))
echo -n $YELLOW
{
$SHOW "message24"  ; printf "%d.%02d " $MINUTES $SECONDS ; $SHOW "message25"
} 2>&1 | tee -a $LOGFILE
ROOTSIZE=$(get_file_size "$MAINDEST/$ROOTNAME")
KERNELSIZE=$(get_file_size "$MAINDEST/$KERNELNAME")
TOTALSIZE=$((($ROOTSIZE+$KERNELSIZE)/1024))
SPEED=$(( $TOTALSIZE/$DIFF ))
echo $SPEED > $LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/speed.txt
echo $LINE >> $LOGFILE
# "Back up done with $SPEED KB per second"
{
$SHOW "message26" ; echo -n "$SPEED" ; $SHOW "message27"
} 2>&1 | tee -a $LOGFILE

#### ADD A LIST OF THE INSTALLED PACKAGES TO THE BackupSuite.LOG ####
echo $LINE >> $LOGFILE
echo $LINE >> $LOGFILE
$SHOW "message41" >> $LOGFILE
echo "--------------------------------------------" >> $LOGFILE
opkg list-installed >> $LOGFILE

######################## COPY LOGFILE TO MAINDESTINATION ######################
echo -n $WHITE
cp $LOGFILE "$MAINDEST"
if  [ "$HARDDISK" != 1 ]; then
    cp $LOGFILE "$MEDIA$EXTR1"
    mv "$MEDIA$EXTR1$FOLDER"/imageversion "$MEDIA$EXTR1"
else
    mv -f "$MAINDEST"/BackupSuite.log "$MEDIA$EXTR1"
    cp "$MAINDEST"/imageversion "$MEDIA$EXTR1"
fi
if [ "$TARGET" != "XX" ] ; then
    cp $LOGFILE "$TARGET$FOLDER"
fi
}

############################## DM9X0 Situation ##############################
if [ "$SEARCH" = "dm900" ] || [ "$SEARCH" = "dm920" ] ; then
    dm9x0_situation
fi

######################## DM52X,DM7080,DM820 Situation ########################
dm52x_dm7080_dm820_situation()
{
log "Found dm52x,dm7080,dm820, xz mode"
EXTRA="$MEDIA/fullbackup_dreambox/$DATE"
MAINDEST="$MEDIA/$SEARCH"
log "Destination        = $MAINDEST"
log $LINE

############# START TO SHOW SOME INFORMATION ABOUT BRAND & MODEL ##############
echo -n $PURPLE
echo -n "$SEARCH " | tr  a-z A-Z        # Shows the receiver brand and model
$SHOW "message02"              # BACK-UP TOOL FOR MAKING A COMPLETE BACK-UP
echo $BLUE
log "RECEIVER = $SEARCH "
echo "$VERSION"
echo $WHITE

############ CALCULATE SIZE, ESTIMATED SPEED AND SHOW IT ON SCREEN ############
$SHOW "message06"     #"Some information about the task:"
KERNELHEX=800000 # Not the real size (will be added later)
KERNEL=$((0x$KERNELHEX))           # Total Kernel size in bytes
TOTAL=$(($USEDsizebytes+$KERNEL))  # Total ROOTFS + Kernel size in bytes
KILOBYTES=$(($TOTAL/1024))         # Total ROOTFS + Kernel size in KB
MEGABYTES=$(($KILOBYTES/1024))
{
echo -n "KERNEL" ; $SHOW "message04" ; printf '%6s' $(($KERNEL/1024)); echo ' KB'
echo -n "ROOTFS" ; $SHOW "message04" ; printf '%6s' $USEDsizekb; echo ' KB'
echo -n "=TOTAL" ; $SHOW "message04" ; printf '%6s' $KILOBYTES; echo " KB (= $MEGABYTES MB)"
} 2>&1 | tee -a $LOGFILE
ESTTIMESEC=$(($KILOBYTES/$ESTSPEED))
ESTMINUTES=$(( $ESTTIMESEC/60 ))
ESTSECONDS=$(( $ESTTIMESEC-(( 60*$ESTMINUTES ))))
echo $LINE
{
$SHOW "message03"  ; printf "%d.%02d " $ESTMINUTES $ESTSECONDS ; $SHOW "message25" # estimated time in minutes
echo $LINE
} 2>&1 | tee -a $LOGFILE

##################### PREPARING THE BUILDING ENVIRONMENT ######################
log "*** FIRST SOME HOUSEKEEPING ***"
mb_safe_rmtree "$WORKDIR" || big_fail       # GETTING RID OF THE OLD REMAINS IF ANY
log "Remove directory   = $WORKDIR"
mkdir -p "$WORKDIR"     # MAKING THE WORKING FOLDER WHERE EVERYTHING HAPPENS
log "Recreate directory = $WORKDIR"
mkdir -p /tmp/bi/root # this is where the complete content will be available
log "Create directory   = /tmp/bi/root"
sync
mb_bind_root /tmp/bi/root || big_fail   # read-only bind of the complete root
# Samba runtime sockets are not files: never back them up and never touch
# them on the live system (/tmp/bi/root is a bind mount of /)
TAR_EXCLUDES="--exclude=./var/lib/samba/msg.sock --exclude=./var/lib/samba/private/msg.sock --exclude=./var/nmbd"
# busybox tar may be built without --exclude: then just skip the excludes
"$(mb_tool tar)" --help 2>&1 | grep -q -- "--exclude" || TAR_EXCLUDES=""

#############################  MAKING ROOT.UBI(FS) ############################
$SHOW "message06a" 2>&1 | tee -a $LOGFILE       #Create: root.ubifs
log $LINE
$MKFS -cf "$WORKDIR/rootfs.tar" -C /tmp/bi/root $TAR_EXCLUDES .

############################ ASSEMBLING THE IMAGE #############################
make_folders
image_version > "$MAINDEST/imageversion"
if  [ "$HARDDISK" != 1 ]; then
    mkdir -p "$EXTRA"
    log "Created directory  = $EXTRA"
    cp -r "$MAINDEST" "$EXTRA"   #copy the made back-up to images
fi
backup_made
$SHOW "message14"            # Instructions on how to restore the image.
echo $LINE

#################### CHECKING FOR AN EXTRA BACKUP STORAGE #####################
if  [ "$HARDDISK" = 1 ]; then                     # looking for a valid usb-stick
    for candidate in $(cut -d ' ' -f 2 /proc/mounts | grep '^/media/')
    do
        [ "$candidate" = "$MEDIA" ] && continue
        for marker in "${candidate}/"*[Bb][Aa][Cc][Kk][Uu][Pp][Ss][Tt][Ii][Cc][Kk]* ; do
            [ -e "$marker" ] && TARGET="${candidate}"
        done
    done
    if [ "$TARGET" != "XX" ] ; then
        echo -n $GREEN
        $SHOW "message17" 2>&1 | tee -a $LOGFILE    # Valid USB-flashdrive detected, making an extra copy
        echo $LINE
        TOTALSIZE="$(df -h "$TARGET" | tail -n 1 | awk {'print $2'})"
        FREESIZE="$(df -h "$TARGET" | tail -n 1 | awk {'print $4'})"
        {
        $SHOW "message09" ; echo -n "$TARGET ($TOTALSIZE, " ; $SHOW "message16" ; echo "$FREESIZE)"
        } 2>&1 | tee -a $LOGFILE
        safe_rm "$TARGET$FOLDER"
        mkdir -p "$TARGET$FOLDER"
        cp -r "$MAINDEST/." "$TARGET$FOLDER"
        echo $LINE >> $LOGFILE
        echo "MADE AN EXTRA COPY IN: $TARGET" >> $LOGFILE
        df -h "$TARGET"  >> $LOGFILE
        $SHOW "message19" 2>&1 | tee -a $LOGFILE    # Backup finished and copied to your USB-flashdrive
    else
        $SHOW "message40" >> $LOGFILE
    fi
sync
fi

################## CLEANING UP AND REPORTING SOME STATISTICS ##################
clean_up
END=$(date +%s)
DIFF=$(( $END - $START ))
MINUTES=$(( $DIFF/60 ))
SECONDS=$(( $DIFF-(( 60*$MINUTES ))))
echo -n $YELLOW
{
$SHOW "message24"  ; printf "%d.%02d " $MINUTES $SECONDS ; $SHOW "message25"
} 2>&1 | tee -a $LOGFILE
ROOTSIZE=$(get_file_size "$MAINDEST/$ROOTNAME")
KERNELSIZE=$(get_file_size "$MAINDEST/$KERNELNAME")
TOTALSIZE=$((($ROOTSIZE+$KERNELSIZE)/1024))
SPEED=$(( $TOTALSIZE/$DIFF ))
echo $SPEED > $LIBDIR/enigma2/python/Plugins/Extensions/BackupSuite/speed.txt
echo $LINE >> $LOGFILE
# "Back up done with $SPEED KB per second"
{
$SHOW "message26" ; echo -n "$SPEED" ; $SHOW "message27"
} 2>&1 | tee -a $LOGFILE

#### ADD A LIST OF THE INSTALLED PACKAGES TO THE BackupSuite.LOG ####
echo $LINE >> $LOGFILE
echo $LINE >> $LOGFILE
$SHOW "message41" >> $LOGFILE
echo "--------------------------------------------" >> $LOGFILE
opkg list-installed >> $LOGFILE

######################## COPY LOGFILE TO MAINDESTINATION ######################
echo -n $WHITE
cp $LOGFILE "$MAINDEST"
if  [ "$HARDDISK" != 1 ]; then
    cp $LOGFILE "$MEDIA"
    mv "$MEDIA$FOLDER"/imageversion "$MEDIA"
else
    mv -f "$MAINDEST"/BackupSuite.log "$MEDIA"
    cp "$MAINDEST"/imageversion "$MEDIA"
fi
if [ "$TARGET" != "XX" ] ; then
    cp $LOGFILE "$TARGET$FOLDER"
fi
}

######################## DM52X,DM7080,DM820 Situation ########################
if [ "$SEARCH" = "dm520" ] || [ "$SEARCH" = "dm525" ] || [ "$SEARCH" = "dm7080" ] || [ "$SEARCH" = "dm820" ] ; then
    dm52x_dm7080_dm820_situation
fi

########################### Old Dreambox Situation ###########################
old_dreambox_situation()
{
log "Found old dreamboxes, nfi mode"
###### TESTING IF ALL THE BINARIES FOR THE BUILDING PROCESS ARE PRESENT #######
echo $RED
checkbinary $MKFSJFFS2
checkbinary $BUILDIMAGE
echo -n $WHITE

############# START TO SHOW SOME INFORMATION ABOUT BRAND & MODEL ##############
echo -n $PURPLE
echo -n "$SEARCH " | tr  a-z A-Z        # Shows the receiver brand and model
$SHOW "message02"              # BACK-UP TOOL FOR MAKING A COMPLETE BACK-UP
echo $BLUE
log "RECEIVER = $SEARCH "
echo "$VERSION"
echo $WHITE

############ CALCULATE SIZE, ESTIMATED SPEED AND SHOW IT ON SCREEN ############
# athoik's code, Modified by Persian Prince #
# Optional, from the environment only (the positional args are media/type/lang)
CREATE_ZIP="${CREATE_ZIP:-}"
IMAGENAME="${IMAGENAME:-backup}"
cleanup_mounts(){
   if [ ! -z "$TBI" ] ; then
      if [ -d "$TBI/boot" ] ; then
     if mb_is_mounted "$TBI/boot" ; then
        mb_unmount_all "$TBI/boot" || { log "Cannot umount boot" ; exit 6 ; }
     fi
     rmdir "$TBI/boot" 2>/dev/null
      fi
      if [ -d "$TBI/root" ] ; then
     if mb_is_mounted "$TBI/root" ; then
        mb_unmount_all "$TBI/root" || { log "Cannot umount root" ; exit 7 ; }
     fi
     rmdir "$TBI/root" 2>/dev/null
      fi
   fi
}
#
# Set Backup Location
#
EXTRA="$MEDIA/fullbackup_dreambox/$DATE"
MAINDEST="$MEDIA/$SEARCH"
SBI="$MEDIA/.backupsuite_work"
TBI="/tmp/bi"
#
# Initialize Parameters
#
EXTRA_BUILDCMD=""
EXTRA_IMAGECMD=""
DREAMBOX_ERASE_BLOCK_SIZE=""
DREAMBOX_FLASH_SIZE=""
DREAMBOX_SECTOR_SIZE=""
MKUBIFS_ARGS=""
UBINIZE_ARGS=""
UBINIZE_VOLSIZE="0"
UBINIZE_DATAVOLSIZE="0"
UBI_VOLNAME="rootfs"
DREAMBOX_IMAGE_SIZE=""
DREAMBOX_PART0_SIZE=""
DREAMBOX_PART1_SIZE=""
DREAMBOX_PART2_SIZE=""
#
# Set parameters based on box
# dm7020hdv2 is recognized from /sys/devices/virtual/mtd/mtd0/writesize
case $SEARCH in
   dm800|dm500hd|dm800se)
      EXTRA_BUILDCMD="--brcmnand"
      DREAMBOX_ERASE_BLOCK_SIZE="0x4000"
      DREAMBOX_FLASH_SIZE="0x4000000"
      DREAMBOX_SECTOR_SIZE="512"
      MKUBIFS_ARGS="-m 512 -e 15KiB -c 3798 -x favor_lzo -X 1 -F -j 4MiB"
      UBINIZE_ARGS="-m 512 -p 16KiB -s 512"
      DREAMBOX_IMAGE_SIZE="64"
      DREAMBOX_PART0_SIZE="0x40000"
      DREAMBOX_PART1_SIZE="0x3C0000"
      DREAMBOX_PART2_SIZE="0x3C00000"
      ;;
   dm500hdv2|dm800sev2|dm7020hdv2)
      EXTRA_BUILDCMD="--hw-ecc --brcmnand"
      DREAMBOX_ERASE_BLOCK_SIZE="0x20000"
      DREAMBOX_FLASH_SIZE="0x40000000"
      DREAMBOX_SECTOR_SIZE="2048"
      MKUBIFS_ARGS="-m 2048 -e 124KiB -c 3320 -x favor_lzo -F"
      UBINIZE_ARGS="-m 2048 -p 128KiB -s 2048"
      UBINIZE_VOLSIZE="402MiB"
      UBINIZE_DATAVOLSIZE="569MiB"
      DREAMBOX_IMAGE_SIZE="1024"
      DREAMBOX_PART0_SIZE="0x100000"
      DREAMBOX_PART1_SIZE="0x700000"
      DREAMBOX_PART2_SIZE="0x3F800000"
      ;;
   dm7020hd)
      EXTRA_BUILDCMD="--hw-ecc --brcmnand"
      DREAMBOX_ERASE_BLOCK_SIZE="0x40000"
      DREAMBOX_FLASH_SIZE="0x40000000"
      DREAMBOX_SECTOR_SIZE="4096"
      MKUBIFS_ARGS="-m 4096 -e 248KiB -c 1640 -x favor_lzo -F"
      UBINIZE_ARGS="-m 4096 -p 256KiB -s 4096"
      UBINIZE_VOLSIZE="397MiB"
      UBINIZE_DATAVOLSIZE="574MiB"
      DREAMBOX_IMAGE_SIZE="1024"
      DREAMBOX_PART0_SIZE="0x100000"
      DREAMBOX_PART1_SIZE="0x700000"
      DREAMBOX_PART2_SIZE="0x3F800000"
      # dm7020hdv2 when writesize = 2048
      WRITESIZE="4096"
      if [ -f /sys/devices/virtual/mtd/mtd0/writesize ] ; then
     WRITESIZE=$(cat /sys/devices/virtual/mtd/mtd0/writesize)
      fi
      if [ "$WRITESIZE" = "2048" ] ; then
     log "Found dm7020hdv2"
     DREAMBOX_ERASE_BLOCK_SIZE="0x20000"
     DREAMBOX_SECTOR_SIZE="2048"
     MKUBIFS_ARGS="-m 2048 -e 124KiB -c 3320 -x favor_lzo -F"
     UBINIZE_ARGS="-m 2048 -p 128KiB -s 2048"
     UBINIZE_VOLSIZE="402MiB"
     UBINIZE_DATAVOLSIZE="569MiB"
      fi
      ;;
   dm8000)
      EXTRA_BUILDCMD=""
      DREAMBOX_ERASE_BLOCK_SIZE="0x20000"
      DREAMBOX_FLASH_SIZE="0x10000000"
      DREAMBOX_SECTOR_SIZE="2048"
      MKUBIFS_ARGS="-m 2048 -e 126KiB -c 1961 -x favor_lzo -F"
      UBINIZE_ARGS="-m 2048 -p 128KiB -s 512"
      DREAMBOX_IMAGE_SIZE="256"
      DREAMBOX_PART0_SIZE="0x100000"
      DREAMBOX_PART1_SIZE="0x700000"
      DREAMBOX_PART2_SIZE="0xF800000"
      ;;
   *)
      log "Error: Unknown dreambox?"
      exit 3
      ;;
esac
EXTRA_IMAGECMD="-e $DREAMBOX_ERASE_BLOCK_SIZE -n -l"
#
# Setup temporary files and variables
#
SECSTAGE="$SBI/secondstage.bin"
UBINIZE_CFG="$TBI/ubinize.cfg"
BOOT="$SBI/boot.jffs2"
ROOTFS="$SBI/rootfs.jffs2"
cleanup_mounts
echo $LINE
echo "Starting Full Backup, Please wait ..."
echo $LINE
mb_safe_rmtree "$SBI" 2>/dev/null
mb_safe_rmtree "$TBI" 2>/dev/null
mkdir -p "$SBI"
mkdir -p "$TBI"
#
# Export secondstage
#
log "Exporting secondstage"
$NANDDUMP --noecc --omitoob --bb=skipbad --file="$SECSTAGE" /dev/mtd1
if [ $? -ne 0 ] && [ ! -f "$SECSTAGE" ] ; then
   mb_safe_rmtree "$SBI" 2>/dev/null
   mb_safe_rmtree "$TBI" 2>/dev/null
   log "Error: nanddump failed to dump secondstage!"
   exit 8
fi
#
# Trim 0xFFFFFF from secondstage
#
$PYTHON -c "
data=open('$SECSTAGE', 'rb').read()
cutoff=data.find(b'\xff\xff\xff\xff')
if cutoff > 0:
    open('$SECSTAGE', 'wb').write(data[0:cutoff])
"
SIZE="$(du -k "$SECSTAGE" | awk '{ print $1 }')"
if [ "$SIZE" -gt 200 ] ; then
   log "Error: Size of secondstage must be less than 200k"
   log "Reinstall secondstage before creating backup"
   log "opkg install --force-reinstall dreambox-secondstage-$SEARCH"
   mb_safe_rmtree "$SBI" 2>/dev/null
   mb_safe_rmtree "$TBI" 2>/dev/null
   exit 9
fi
#
# Export boot partition
#
log "Exporting boot partition"
mkdir -p "$TBI/boot"
mount -t jffs2 -o ro /dev/mtdblock/2 "$TBI/boot"
$MKFSJFFS2 \
   --root="$TBI/boot" \
   --compression-mode=none \
   --output="$BOOT" \
   $EXTRA_IMAGECMD
mb_unmount_all "$TBI/boot"
#
# Export root partition
#
if grep -q ubi0:rootfs /proc/mounts ; then
   log "Exporting rootfs (UBI)"
   ROOTFS="$SBI/rootfs.ubi"
   ROOTUBIFS="$SBI/rootfs.ubifs"
   mkdir -p "$TBI/root"
   mb_bind_root "$TBI/root" || exit 7
   echo [root] > $UBINIZE_CFG
   echo mode=ubi >> $UBINIZE_CFG
   echo image=$ROOTUBIFS >> $UBINIZE_CFG
   echo vol_id=0 >> $UBINIZE_CFG
   echo vol_name=$UBI_VOLNAME >> $UBINIZE_CFG
   echo vol_type=dynamic >> $UBINIZE_CFG
   if [ "$UBINIZE_VOLSIZE" = "0" ] ; then
      echo vol_flags=autoresize >> $UBINIZE_CFG
   else
      echo vol_size=$UBINIZE_VOLSIZE >> $UBINIZE_CFG
      if [ "$UBINIZE_DATAVOLSIZE" != "0" ] ; then
     echo [data] >> $UBINIZE_CFG
     echo mode=ubi >> $UBINIZE_CFG
     echo vol_id=1 >> $UBINIZE_CFG
     echo vol_type=dynamic >> $UBINIZE_CFG
     echo vol_name=data >> $UBINIZE_CFG
     echo vol_size=$UBINIZE_DATAVOLSIZE >> $UBINIZE_CFG
     echo vol_flags=autoresize >> $UBINIZE_CFG
      fi
   fi
   "$(mb_tool mkfs.ubifs)" -r "$TBI/root" -o $ROOTUBIFS $MKUBIFS_ARGS
   log "mkfs.ubifs return value: $?"
   "$UBINIZE" -o $ROOTFS $UBINIZE_ARGS $UBINIZE_CFG
   log "ubinize return value: $?"
   mb_unmount_all "$TBI/root"
else
   log "Export rootfs (JFFS2)"
   mkdir -p "$TBI/root"
   mount -t jffs2 -o ro /dev/mtdblock/3 "$TBI/root"
   $MKFSJFFS2 \
      --root="$TBI/root" \
      --disable-compressor=lzo \
      --compression-mode=size \
      --output=$ROOTFS \
      $EXTRA_IMAGECMD
   log "mkfs.jffs2 return value: $?"
   mb_unmount_all "$TBI/root"
fi
#
# Build NFI image
#
log "Building NFI image"
$BUILDIMAGE --arch $SEARCH $EXTRA_BUILDCMD \
   --erase-block-size $DREAMBOX_ERASE_BLOCK_SIZE \
   --flash-size $DREAMBOX_FLASH_SIZE \
   --sector-size $DREAMBOX_SECTOR_SIZE \
   --boot-partition $DREAMBOX_PART0_SIZE:$SECSTAGE \
   --data-partition $DREAMBOX_PART1_SIZE:$BOOT \
   --data-partition $DREAMBOX_PART2_SIZE:$ROOTFS \
   > "$SBI/backup.nfi"
#
# Archive NFI image
#
log "Transfering image to backup folder"
TSTAMP="$(date "+%Y-%m-%d-%Hh%Mm")"
safe_rm "$MAINDEST"
mkdir -p "$MAINDEST"
NFI="$MAINDEST/$TSTAMP-$SEARCH.nfi"
mv "$SBI/backup.nfi" "$NFI"
log "Backup image created $NFI"
log "$(du -h $NFI)"
if [ -z "$CREATE_ZIP" ] ; then
   mkdir -p "$EXTRA"
   cp -r "$NFI" "$EXTRA"
   touch "$MEDIA/fullbackup/.timestamp"
else
   if [ "$CREATE_ZIP" != "none" ] ; then
      log "Create zip archive..."
      ( cd "$MEDIA" && $CREATE_ZIP -r "$MEDIA/backup-$IMAGENAME-$SEARCH-$TSTAMP.zip" "$SEARCH" )
   fi
fi
#
# Cleanup
#
log "Remove temporary files..."
cleanup_mounts
mb_safe_rmtree "$SBI" 2>/dev/null
mb_safe_rmtree "$TBI" 2>/dev/null
if [ -f "$NFI" ] ; then
    backup_made_nfi
else
    echo $RED
    $SHOW "message15" 2>&1 | tee -a $LOGFILE # Image creation FAILED!
    echo $WHITE
    exit 1
fi
#
# The End
#
log "Completed!"

################## CLEANING UP AND REPORTING SOME STATISTICS ##################
clean_up
END=$(date +%s)
DIFF=$(( $END - $START ))
MINUTES=$(( $DIFF/60 ))
SECONDS=$(( $DIFF-(( 60*$MINUTES ))))
echo -n $YELLOW
{
$SHOW "message24"  ; printf "%d.%02d " $MINUTES $SECONDS ; $SHOW "message25"
} 2>&1 | tee -a $LOGFILE

#### ADD A LIST OF THE INSTALLED PACKAGES TO THE BackupSuite.LOG ####
echo $LINE >> $LOGFILE
echo $LINE >> $LOGFILE
$SHOW "message41" >> $LOGFILE
echo "--------------------------------------------" >> $LOGFILE
opkg list-installed >> $LOGFILE
}

########################### Old Dreambox Situation ###########################
if [ "$SEARCH" != "dm900" ] && [ "$SEARCH" != "dm920" ] && [ "$SEARCH" != "dm520" ] && [ "$SEARCH" != "dm525" ] && [ "$SEARCH" != "dm7080" ] && [ "$SEARCH" != "dm820" ] ; then
    old_dreambox_situation
fi

exit 0

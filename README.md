# Jellyfin Kiosk Appliance Builder (JKAB)

*JKAB, pronounced "Jakob" in Australian*

Zero-config distro image for a Jellyfin kiosk appliance. Boots straight into
Jellyfin Media Player in fullscreen with a local Jellyfin server running.
Plug in a USB drive or SD card with media files and they appear in the library
automatically.

Based on Debian 13 (trixie) cloud image, provisioned with cloud-init and built
using [cijoe](https://github.com/refenv/cijoe).

## What's in the image

- **System user**: `jellyfin` / `jellyfin`
  - XFCE4 auto-login via LightDM
  - Passwordless sudo
- **Jellyfin user**: `Jellyfin` / `jellyfin` (created automatically on first boot)
- **Server**: Jellyfin media server with optimized ffmpeg (auto-starts, auto-configured)
- **Client**: Jellyfin Media Player in fullscreen (native deb)
- **Network**: NetworkManager with tray applet for WiFi/Ethernet configuration
- **HDMI CEC**: cec-client bridge translating TV remote keys to keyboard events
- **Media**: USB/SD auto-mount to `/media/` and trigger library scan
- **Metadata**: saved alongside media files (survives image reflash)
- **Firmware**: non-free firmware for broad GPU/WiFi hardware support
- **HiDPI**: auto-detects 4K displays and scales Jellyfin Media Player UI to 2x
- **Display**: screensaver, DPMS, and screen blanking disabled; cursor hidden after 1s
- **Power button**: clean shutdown via systemd-logind
- **Audio**: PulseAudio
- **Filesystem**: NTFS and exFAT support for external media
- **Updates**: disabled — update by reflashing the image
- **Debug**: SSH enabled (root/root)
- **Sample**: Big Buck Bunny trailer included for playback testing

## Install

1. Download a live USB image (e.g. [Ubuntu Desktop](https://ubuntu.com/download/desktop))
   and boot the target machine from it

2. Open a terminal and identify the target drive:

   ```bash
   lsblk
   ```

3. Download and write the appliance image directly to the drive (replace `/dev/nvme0n1`):

   ```bash
   wget -qO- https://github.com/safl/jellyfin-kiosk-appliance-builder/releases/latest/download/jkab-x86_64.raw.gz | \
     gunzip | sudo dd of=/dev/nvme0n1 bs=4M status=progress
   ```

4. Reboot into the installed appliance:

   ```bash
   reboot
   ```

5. On first boot, the appliance auto-logs in, sets up the Jellyfin server,
   and launches the media player. Plug in a USB drive or SD card with media
   files — they auto-mount and appear in the library.

   Jellyfin login: **Jellyfin** / **jellyfin**

## Build from source

### Prerequisites

- QEMU (`qemu-system-x86_64`, `qemu-img`)
- `mkisofs` (from `cdrtools` or `genisoimage`)

### Build

```bash
make deps      # install build dependencies (cijoe via pipx)
make build     # build the disk image
make clean     # remove build artifacts
```

The baked qcow2 image will be at `~/system_imaging/disk/jkab-x86_64.qcow2`.

### Configuration

Edit `configs/config.toml` to adjust:

- **RAM/CPU**: `system_args.kwa` in `[qemu.guests.jkab-x86_64]`
- **SSH port**: `system_args.tcp_forward`

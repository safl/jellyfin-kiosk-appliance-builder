# Jellyfin Kiosk Appliance Builder (JKAB)

*JKAB, pronounced "Jakob" in Australian*

Zero-config distro image for a Jellyfin kiosk appliance. Boots straight into
Jellyfin Media Player in fullscreen with a local Jellyfin server running.
Plug in a USB drive or SD card with media files and they appear in the library
automatically.

Based on Debian 13 (trixie) cloud image, provisioned with cloud-init and built
using [cijoe](https://github.com/refenv/cijoe). Currently targets x86_64
NUC-style hardware with Intel GPU drivers. Could be expanded, upon request,
to support other hardware such as Raspberry Pi 4/5, AMD-based NUCs, etc.

## What's in the image

### Jellyfin

- **Server**: Jellyfin media server with optimized ffmpeg (auto-starts, auto-configured)
- **Client**: Jellyfin Media Player in fullscreen (native deb)
- **Jellyfin user**: `jellyfin` / `jellyfin` (created automatically on first boot)
- **Metadata**: saved alongside media files (survives image reflash)
- **Sample**: Big Buck Bunny trailer included for playback testing

### Display

- **Kiosk**: openbox window manager, no desktop environment
- **HiDPI**: auto-detects 4K displays and scales UI to 2x
- **Screensaver/DPMS**: disabled, cursor hidden after 1s idle
- **HDMI CEC**: cec-client bridge translating TV remote keys to keyboard events

### Library & Media

- **Libraries**: Movies and Shows libraries created on first boot, both pointing to `/media/`
- **Metadata**: fetched in the configured locale and saved alongside media files (survives reflash)
- **Auto-mount**: USB/SD drives auto-mount to `/media/<device>` via udev rules and udisks2
- **Library scan**: Jellyfin server detects new mounts and rescans automatically
- **Filesystem**: NTFS and exFAT support for external media

### System

- **System user**: `jellyfin` / `jellyfin` (auto-login, passwordless sudo)
- **Network**: NetworkManager (configure via `nmtui` over SSH)
- **Audio**: PulseAudio
- **GPU**: Intel VA-API hardware video decoding
- **Power button**: clean shutdown via systemd-logind
- **Updates**: disabled — update by reflashing the image
- **Debug**: SSH enabled (root/root)

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
   and launches the media player. On the first launch, connect to
   `localhost:8096` and log in with **jellyfin** / **jellyfin**. The client
   remembers the server on subsequent boots.

   Plug in a USB drive or SD card with media files — they auto-mount and
   appear in the library.

## Install extras

The image ships without diagnostic tools to keep the size down.
To install them after flashing, SSH in and run:

```bash
jkab-install-extras.sh
```

This adds: `intel-gpu-tools`, `mesa-utils`, `psmisc`, `va-driver-all`, and `vainfo`.

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

The baked qcow2 image will be at `~/system_imaging/disk/jkab-dk-x86_64.qcow2`.

### Run locally

Requires a built image (`make build`). Boots the image in QEMU with a SPICE display:

```bash
make run
```

Then connect with a SPICE client on port 5930:

```bash
sudo apt-get install -qy virt-viewer
remote-viewer spice://localhost:5930
```

### Configuration

Edit `configs/dk.toml` (or create a new variant) to adjust:

- **Locale**: `[jkab]` section (UI culture, metadata language, timezone, subtitle/audio prefs)
- **RAM/CPU**: `system_args.kwa` in the `[qemu.guests.*]` section
- **SSH port**: `system_args.tcp_forward`

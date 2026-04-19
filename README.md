# Janky Kiosk Appliance Builder (JKAB)

*JKAB, pronounced "Jakob" in Australian*

Zero-config distro image for a Netflix-style media kiosk. Boots straight into a
custom grid-based UI for browsing and playing video from `/media/` drives.
Metadata is provided offline via `.nfo` files (created by MediaElch on a separate machine).
Plug in a USB drive or SD card with pre-indexed media and it plays immediately.

Based on Debian 13 (trixie) cloud image, provisioned with cloud-init and built
using [cijoe](https://github.com/refenv/cijoe). Currently targets x86_64
NUC-style hardware with Intel GPU drivers. Could be expanded, upon request,
to support other hardware such as Raspberry Pi 4/5, AMD-based NUCs, etc.

## What's in the image

### Media Player

- **Server**: Lightweight jkab-server (Python Flask) indexing `.nfo` metadata files
- **Client**: Custom Netflix-style grid UI (pygame) with DPad navigation
- **System user**: `jkab` / `jkab` (created automatically)
- **Metadata**: Provided offline via `.nfo` files alongside video (created by MediaElch)
- **Playback**: mpv with hardware video decoding

### Display

- **Kiosk**: openbox window manager, no desktop environment
- **HiDPI**: auto-detects 4K displays and scales UI to 2x
- **Screensaver/DPMS**: disabled, cursor hidden after 1s idle
- **HDMI CEC**: cec-client bridge translating TV remote keys to keyboard events

### Library & Media

- **Structure**: Movies, Shows, Videos folders in `/media/` (created automatically)
- **Metadata**: `.nfo` files + poster art (created by MediaElch on separate machine)
- **Auto-mount**: USB/SD drives auto-mount to `/media/<label>` via udev rules
- **Offline**: All metadata cached locally; no internet required after setup
- **Filesystem**: NTFS and exFAT support for external media

### System

- **System user**: `jkab` / `jkab` (auto-login, passwordless sudo)
- **Network**: NetworkManager (configure via `nmtui` over SSH)
- **Audio**: PulseAudio
- **GPU**: Intel VA-API hardware video decoding
- **Power button**: clean shutdown via systemd-logind
- **Updates**: disabled — update by reflashing the image
- **Debug**: SSH enabled (root/root)

## Install

### Prerequisites

- External media drive (USB or SD card) with video files organized as:
  - `Movies/<title>/<video.mp4>`
  - `Shows/<show>/<season>/<episode.mp4>`
  - `Videos/<collection>/<video.mp4>`

### Setup (one-time, on separate machine)

1. Install [MediaElch](https://github.com/Komet/MediaElch) (free, open-source)
2. Point it at your media drive and fetch metadata from themoviedb.org / thetvdb.com
3. Result: `.nfo` files + poster art alongside each video file

### Deploy to kiosk

1. Download a live USB image (e.g. [Ubuntu Desktop](https://ubuntu.com/download/desktop))
   and boot the target machine from it

2. Open a terminal and identify the target drive:

   ```bash
   lsblk
   ```

3. Download and write the appliance image directly to the drive (replace `/dev/nvme0n1`):

   ```bash
   wget -qO- https://github.com/safl/jellyfin-kiosk-appliance-builder/releases/latest/download/jkab-dk-x86_64.raw.gz | \
     gunzip | sudo dd of=/dev/nvme0n1 bs=4M status=progress
   ```

4. Reboot into the installed appliance:

   ```bash
   reboot
   ```

5. On first boot, the appliance auto-logs in and launches the media player.
   Plug in your media drive (with `.nfo` metadata from MediaElch) — it auto-mounts
   and appears in the grid UI immediately.
   
   Navigate with dpad/remote, select with enter, play with mpv.

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
make deps         # install build dependencies (cijoe via pipx)
make build        # build the disk image
make test         # run test suite on the built image
make clean        # remove build artifacts
```

The baked qcow2 image will be at `~/system_imaging/disk/jkab-dk-x86_64.qcow2`.

### Run locally

Requires a built image (`make build`). Boots the image in QEMU with a SPICE display:

```bash
make interactive
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

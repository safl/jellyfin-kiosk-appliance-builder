<p align="center">
  <img src="assets/tellybox-wordmark.svg" alt="Tellybox" width="220">
</p>

<p align="center">
  <em>A box for your telly.</em>
</p>

<p align="center">
  <a href="https://github.com/safl/tellybox/actions/workflows/build.yml"><img alt="Build" src="https://github.com/safl/tellybox/actions/workflows/build.yml/badge.svg"></a>
  <a href="https://github.com/safl/tellybox/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/safl/tellybox?display_name=tag&label=release&color=E50914"></a>
  <img alt="Debian 13" src="https://img.shields.io/badge/Debian%2013-A81D33?logo=debian&logoColor=white">
  <img alt="Python 3" src="https://img.shields.io/badge/Python%203-3776AB?logo=python&logoColor=white">
  <img alt="Built with cijoe" src="https://img.shields.io/badge/built%20with-cijoe-EB6E2F">
  <img alt="mpv" src="https://img.shields.io/badge/playback-mpv-672A8F">
  <br>
  <img alt="Offline-first" src="https://img.shields.io/badge/offline-first-E50914">
  <img alt="Zero config" src="https://img.shields.io/badge/setup-zero%20config-success">
  <img alt="HDMI CEC remote" src="https://img.shields.io/badge/remote-HDMI%20CEC-blue">
  <img alt="x86_64" src="https://img.shields.io/badge/arch-x86__64-lightgrey">
</p>

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

- **Server**: Lightweight tellybox-server (Python Flask) indexing `.nfo` metadata files
- **Client**: Custom Netflix-style grid UI (pygame) with DPad navigation
- **System user**: `tellybox` / `tellybox` (created automatically)
- **Metadata**: Provided offline via `.nfo` files alongside video (created by MediaElch)
- **Playback**: mpv with hardware video decoding

### Display

- **Kiosk**: openbox window manager, no desktop environment
- **HiDPI**: auto-detects 4K displays and scales UI to 2x
- **Screensaver/DPMS**: disabled, cursor hidden after 1s idle
- **HDMI CEC**: cec-client bridge translating TV remote keys to keyboard events

### Library & Media

- **Media Library**: every drive under `/media/` is one source. Top-level
  folder names on each drive become **Collections** (Movies, Shows, Yoga,
  Documentaries, …). Same-named collections from multiple drives are merged.
- **Metadata**: `.nfo` files + poster art alongside the videos (created by
  MediaElch on a separate machine — see [Building a media library](#building-a-media-library))
- **Auto-mount**: USB/SD drives auto-mount to `/media/<label>` via udev rules
- **Offline**: all metadata cached on the drive; no internet required after setup
- **Filesystem**: NTFS and exFAT support for external media

### System

- **System user**: `tellybox` / `tellybox` (auto-login, passwordless sudo)
- **Network**: NetworkManager (configure via `nmtui` over SSH)
- **Audio**: PulseAudio
- **GPU**: Intel VA-API hardware video decoding
- **Power button**: clean shutdown via systemd-logind
- **Updates**: disabled — update by reflashing the image
- **Debug**: SSH enabled (root/root)

## Building a media library

The kiosk image ships **empty** — no built-in samples, no scraping. Prepare
your drive on another machine once, then plug it in.

### Drive layout

Any drive (USB stick, SSD, SD card) is treated as a Media Library *source*.
Each top-level folder on the drive becomes a Collection in the UI, so name
them however you want — `Movies`, `Shows`, `Yoga`, `Documentaries`,
`Concerts`, etc. Multiple drives with the same Collection name (e.g., two
drives both have a `Movies/` folder) merge automatically.

Inside each Collection, follow the same conventions Kodi uses, so a single
scrape works for both Kodi and Tellybox.

```
MyDrive/
├── Movies/
│   ├── Fletch (1985)/
│   │   ├── Fletch.mkv
│   │   ├── Fletch.nfo
│   │   ├── Fletch-poster.jpg
│   │   ├── Fletch-fanart.jpg
│   │   └── Fletch-thumb.jpg
│   └── Big Buck Bunny (2008)/
│       ├── big_buck_bunny.mkv
│       ├── big_buck_bunny.nfo
│       └── big_buck_bunny-poster.jpg
├── Shows/
│   └── Columbo/
│       ├── tvshow.nfo
│       ├── poster.jpg
│       ├── fanart.jpg
│       ├── season05-poster.jpg
│       └── Season 05/
│           ├── Columbo S05E01.mkv
│           ├── Columbo S05E01.nfo
│           └── Columbo S05E01-thumb.jpg
└── Yoga/
    └── David Swenson/
        ├── tvshow.nfo
        ├── poster.jpg
        └── Season 01/
            ├── Lesson 01.mkv
            └── Lesson 01.nfo
```

A movie folder containing **exactly one** video file collapses into a single
playable entry, so `Fletch (1985)/` shows up as one tile (not a folder you
have to descend into) and clicking it opens the details view.

### Generating .nfo and artwork with MediaElch

1. Install [MediaElch](https://github.com/Komet/MediaElch) (free, open-source)
2. Add your drive's `Movies/` folder as a Movie Source, and `Shows/` as a TV Source
3. Use **Search** (single title) or **Scan** (whole folder) to fetch metadata
   from themoviedb.org / thetvdb.com
4. Save with **Movie Files**: `MovieName/MovieName.{ext}` and **TV Show Files**:
   `Show/Season X/Show SXXEYY.{ext}` — these are MediaElch's defaults and what
   Tellybox expects
5. Enable poster, fanart, and thumb downloads in MediaElch's settings — Tellybox
   recognises both Kodi MovieFolder names (`<title>-poster.jpg`) and the
   generic ones (`poster.jpg`, `cover.jpg`, `fanart.jpg`)

### Filesystem

The drive can be **NTFS** or **exFAT** (preferred for cross-OS use). Filesystem
labels become the mount point name; avoid labels named `Movies`, `Shows`, etc.
since those collide with Collection names — Tellybox will rename them with a
numeric suffix if needed.

## Install

### Deploy to kiosk

1. Download a live USB image (e.g. [Ubuntu Desktop](https://ubuntu.com/download/desktop))
   and boot the target machine from it

2. Open a terminal and identify the target drive:

   ```bash
   lsblk
   ```

3. Download and write the appliance image directly to the drive (replace `/dev/nvme0n1`):

   ```bash
   wget -qO- https://github.com/safl/tellybox/releases/latest/download/tellybox-dk-x86_64.raw.gz | \
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
tellybox-install-extras.sh
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

The baked qcow2 image will be at `~/system_imaging/disk/tellybox-dk-x86_64.qcow2`.

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

- **Locale**: `[tellybox]` section (UI culture, metadata language, timezone, subtitle/audio prefs)
- **RAM/CPU**: `system_args.kwa` in the `[qemu.guests.*]` section
- **SSH port**: `system_args.tcp_forward`

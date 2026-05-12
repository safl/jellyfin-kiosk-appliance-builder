# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Tellybox** is a zero-config Debian-based media kiosk appliance image for x86_64 NUC-style hardware. A box for your telly — a small HTPC that plugs into a TV's HDMI port and turns it into a Netflix-style local player.

The image is built on Debian 13 cloud image and provisioned via cloud-init. It boots directly into a custom fullscreen pygame UI (`tellybox-player`) backed by a lightweight local Flask server (`tellybox-server`) that indexes `.nfo` metadata and streams video files. Playback is handled by mpv with VA-API hardware decode.

Metadata is **offline-first**: created on a separate machine using MediaElch (or any KODI-compatible scraper) which writes `.nfo` XML files and poster art alongside videos in `/media/`. The kiosk never touches the internet for metadata.

**Key features:**
- Custom tellybox-server (Flask, indexes `.nfo` files, streams video with HTTP range)
- Custom tellybox-player (pygame Netflix-grid UI with DPad navigation)
- Dynamic tabs for all top-level folders in `/media/` (auto-shows USB mounts)
- HDMI CEC support for TV remote control (cec-utils → xdotool)
- Auto-mounting USB/SD media drives via udev
- HiDPI auto-detection (4K displays)
- mpv with hardware video decoding (Intel VA-API)
- Minimal footprint (no desktop environment, openbox only)
- SSH access for debugging (root/root)

## Build System

Tellybox uses **[cijoe](https://github.com/refenv/cijoe)** — a Python-based build orchestration framework for system imaging. The build process is defined in YAML task files.

### Common Commands

```bash
make deps          # Install cijoe + test dependencies (pipx)
make build         # Build disk image from cloud image
make test          # Run test suite on built image (QEMU guest)
make interactive   # Boot image in QEMU with SPICE display
make clean         # Remove build artifacts (cijoe-output, disk image)
```

All commands accept `VARIANT=xx` to build different regional variants (default: `dk`). Example: `make build VARIANT=us`

**Single variant build without Makefile:**
```bash
cijoe tasks/build.yaml --monitor -c configs/dk.toml
cijoe tasks/test.yaml --monitor -c configs/dk.toml
cijoe tasks/run.yaml --monitor -c configs/dk.toml  # interactive QEMU
```

## Architecture & Build Flow

### Overview

```
Debian 13 cloud image
        ↓
   cloud-init provisioning (userdata)
        ↓ (in QEMU)
   Baked disk image (qcow2)
        ↓
   Deploy to hardware
        ↓
   Plug in /media/ drive (with .nfo from MediaElch)
        ↓
   tellybox-server indexes filesystem, tellybox-player shows grid
```

### Key Build Stages

1. **gen_userdata** (scripts/gen_userdata.py)
   - Combines `auxiliary/cloudinit-base.user` with files from `rootfs/`
   - Files under `/home/tellybox/` get `owner: tellybox:tellybox` and `defer: true` (created after user exists)
   - Templates timezone variable
   - Generates `/etc/tellybox.conf` with locale settings
   - Output: `auxiliary/cloudinit-userdata.user` (DO NOT EDIT manually)

2. **diskimage_build** (scripts/diskimage_build.py)
   - Downloads Debian 13 cloud image (if needed)
   - Resizes disk to 12GB
   - Creates cloud-init seed ISO from metadata + userdata
   - Boots image in QEMU with seed ISO (runs cloud-init provisioning)
   - Compacts final image to qcow2
   - Generates SHA256 checksum

3. **Test Suite** (tests/test_appliance.py via cijoe testrunner)
   - Runs on booted QEMU guest (SSH access)
   - Verifies packages, systemd services, config files
   - Tests tellybox-server health endpoint
   - Tests CEC udev rules, automount rules, scripts executable

## File Structure

```
Tellybox/
├── Makefile                    # Build targets
├── README.md                   # User documentation
├── configs/
│   └── dk.toml                # Build config (locale, QEMU args, image paths)
├── tasks/
│   ├── build.yaml             # Build workflow (gen_userdata → diskimage_build)
│   ├── test.yaml              # Test workflow (run suite on guest)
│   └── run.yaml               # Interactive QEMU (SPICE display)
├── scripts/
│   ├── gen_userdata.py        # Generate cloud-init userdata from rootfs/
│   ├── diskimage_build.py     # Build disk image (download, provision, compact)
│   └── guest_run.py           # Start QEMU with SPICE display
├── rootfs/                    # Files baked into image via cloud-init write_files
│   ├── etc/                   # System config (systemd units, udev rules, autologin)
│   ├── usr/local/bin/         # System scripts (tellybox-server, automount, install-extras)
│   └── home/tellybox/             # User scripts & config (tellybox-player, openbox)
├── auxiliary/
│   ├── cloudinit-base.user    # Base cloud-init config (edit this)
│   ├── cloudinit-userdata.user # Generated userdata (DO NOT EDIT manually)
│   └── cloudinit-metadata.meta # Cloud-init metadata
└── tests/
    └── test_appliance.py      # pytest tests (run on guest via cijoe)
```

## Configuration System

Configuration is **TOML-based** in `configs/*.toml`. Each variant (dk, us, etc.) has its own config file.

### Key Config Sections

**[tellybox]** — Locale & internationalization (written to `/etc/tellybox.conf` on guest)
```toml
[tellybox]
variant = "dk"
ui_culture = "da"              # UI language hint
metadata_country = "DK"        # Metadata region
metadata_language = "da"
subtitle_language = "da"
audio_language = "da"
subtitle_mode = "Smart"
timezone = "Europe/Copenhagen" # Templated into cloud-init
```

**[cijoe.transport.qemu_guest]** — SSH access to guest (port 4200 forwarded to 22)

**[qemu.guests.tellybox-*]** — QEMU VM configuration (CPU, RAM, accel)

**[system-imaging.images.tellybox-*]** — Cloud image URL + disk output path

## Cloud-Init Provisioning

The appliance is provisioned by cloud-init via `auxiliary/cloudinit-userdata.user`.

### Main Provisions:
- **System user**: `tellybox` / `tellybox` (passwordless sudo, auto-login on tty1)
- **Hostname**: `tellybox`
- **Packages**: openbox, xinit, dbus, NetworkManager, intel-media-va-driver, mpv, python3-pygame, libcec-dev, plymouth, openssh-server
- **Pip**: Flask, tomli, tomli-w (for tellybox-server)
- **Media dirs**: `/media/Movies`, `/media/Shows`, `/media/Videos`
- **Cache**: `/home/tellybox/.cache/tellybox` (for tellybox-server progress TOML)
- **CEC**: cec-utils + udev rules for Pulse-Eight CEC adapter
- **Automount**: udisks2 + udev rules for `/media/<label>` USB/SD mounting
- **Boot**: Plymouth splash, quiet kernel, BIOS-safe fstab fixup
- **Systemd**: `tellybox-server.service` enabled (runs as user `tellybox`)
- **Sample Media**: Sintel, Big Buck Bunny → `/media/Misc/` (CC test videos)

### First-Boot Sequence:
1. Cloud-init runs provisioning (packages, scripts, systemd units)
2. User auto-logs in as `tellybox` on tty1
3. `.bash_profile` runs `startx` on tty1
4. `.xinitrc` execs `dbus-run-session openbox-session`
5. openbox `autostart` waits for tellybox-server health check then loops `tellybox-player.py`
6. tellybox-cec-bridge.py runs in background mapping CEC keys to xdotool

## Testing

```bash
make test VARIANT=dk           # Runs on built image in QEMU guest
```

Test coverage in `tests/test_appliance.py`:
- **Packages**: python3, python3-pygame, flask, mpv, openbox, cec-utils, etc.
- **Services**: tellybox-server enabled/active, responds on `localhost:8080/api/health`
- **Kiosk**: tty1 autologin (tellybox), openbox setup, scripts executable
- **Locale**: `/etc/tellybox.conf` generated with correct values
- **Config**: udev CEC + automount rules, logind power button
- **Media**: `/media/{Movies,Shows,Videos}` directories exist, `/home/tellybox/.cache/tellybox` exists

Tests run via **cijoe testrunner** (pytest) over SSH to the QEMU guest.

## Key Scripts & Tools

### rootfs/usr/local/bin/

**tellybox-server.py** — Flask media server (runs as user `tellybox` via systemd)
- Walks `/media/`, parses `.nfo` XML for metadata, serves filesystem-based API
- Endpoints: `/api/health`, `/api/media[/{path}]`, `/stream/{path}`, `/image/{path}`, `/api/progress`
- Streams video with HTTP range support (mpv seeking)
- Listens on `127.0.0.1:8080`

**tellybox-automount.sh** — udev hook for USB/SD media auto-mount to `/media/<label>`

**tellybox-umount.sh** — udev hook for safe unmount

**tellybox-install-extras.sh** — Optional: install diagnostic tools (intel-gpu-tools, vainfo, etc.)

### rootfs/home/tellybox/bin/

**tellybox-player.py** — pygame Netflix-grid UI client
- Queries tellybox-server for media + metadata
- Dynamic tabs for top-level `/media/` folders (so USB mounts auto-appear)
- Grid view → details view → mpv playback (subprocess)
- Reclaims pygame display after mpv exits
- DPad navigation; left/right at grid edges switches tabs

**tellybox-cec-bridge.py** — Maps HDMI CEC remote keys to keyboard via xdotool

## Development Workflow

### Adding a New File to Image
1. Place file in `rootfs/` with correct path/permissions (chmod +x for scripts)
2. `gen_userdata.py` automatically picks it up as cloud-init `write_files` entry
3. Files under `/home/tellybox/` get `owner: tellybox:tellybox` and `defer: true`
4. Run `make build`

### Modifying Cloud-Init Provisioning
1. Edit `auxiliary/cloudinit-base.user` (base YAML) — never edit `cloudinit-userdata.user`
2. Run `make build`

### Creating a New Variant
1. Copy `configs/dk.toml` → `configs/us.toml`
2. Update `[tellybox]` section (ui_culture, timezone, etc.)
3. Build: `make build VARIANT=us`

### Debugging on Booted Image
```bash
ssh -p 4200 root@localhost           # root access (test/interactive mode)
ssh -p 4200 tellybox@localhost           # user account (tellybox/tellybox)
journalctl -u tellybox-server -f         # follow server logs
```

## Build Output

### Artifacts
- **Disk Image**: `~/system_imaging/disk/tellybox-dk-x86_64.qcow2` (main output)
- **SHA256**: `~/system_imaging/disk/tellybox-dk-x86_64.qcow2.sha256`
- **Cloud Image Cache**: `~/system_imaging/cloud/debian-13-generic-amd64-daily.qcow2` (reused between builds)
- **Build Logs**: `cijoe-output/` (task outputs, SSH logs)

### Release Pipeline
Tags matching `v*` push trigger `.github/workflows/build.yml` which builds, tests, converts qcow2 → raw.gz, and uploads as a GitHub Release asset.

### Build Prerequisites
- QEMU (`qemu-system-x86_64`, `qemu-img`)
- mkisofs (from `cdrtools` or `genisoimage`)
- Python 3.10+ with pipx
- ~15GB disk space (cloud image + work + final image)

## Key Dependencies & Technologies

- **cijoe**: Build orchestration (YAML workflows, pytest runner)
- **cloud-init**: VM provisioning via userdata script
- **QEMU/KVM**: Virtual machine for provisioning and testing
- **openbox**: Minimal X11 window manager
- **Flask**: tellybox-server HTTP framework
- **pygame**: tellybox-player UI rendering
- **mpv**: Video playback (hardware accelerated)
- **cec-utils**: HDMI CEC remote control bridge
- **intel-media-va-driver**: Hardware video decoding
- **MediaElch** (external, separate machine): one-time `.nfo` metadata generation

## Related Resources

- **MediaElch**: https://github.com/Komet/MediaElch (offline metadata scraper)
- **cijoe**: https://github.com/refenv/cijoe
- **Cloud-Init**: https://cloudinit.readthedocs.io/
- **Debian Cloud Images**: https://cloud.debian.org/
- **mpv**: https://mpv.io/

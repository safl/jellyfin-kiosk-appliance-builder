# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**JKAB** (Jellyfin Kiosk Appliance Builder) is an automated build system that creates a zero-config Debian-based disk image for running a Jellyfin media server + client kiosk on x86_64 NUC-style hardware.

The image is built on Debian 13 cloud image and provisioned via cloud-init. It boots directly to a fullscreen Jellyfin Media Player instance running in openbox (minimal X11 window manager), with a local Jellyfin server auto-starting in the background.

**Key features:**
- Jellyfin server + Media Player (native debs)
- HDMI CEC support for TV remote control
- Auto-mounting USB/SD media drives
- HiDPI auto-detection (4K displays)
- Minimal footprint (no desktop environment)
- SSH access for debugging

## Build System

JKAB uses **[cijoe](https://github.com/refenv/cijoe)** — a Python-based build orchestration framework for system imaging. The build process is defined in YAML task files.

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
```

### Key Build Stages

1. **gen_userdata** (scripts/gen_userdata.py)
   - Combines `auxiliary/cloudinit-base.user` with files from `rootfs/`
   - Templates timezone variable
   - Generates `/etc/jkab.conf` with locale settings
   - Output: `auxiliary/cloudinit-userdata.user`

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
   - Tests Jellyfin server/client setup and first-boot wizard
   - Tests CEC udev rules, automount rules, scripts executable

## File Structure

```
JKAB/
├── Makefile                    # Build targets
├── README.md                   # User documentation
├── configs/
│   └── dk.toml                # Build config (locale, QEMU args, image paths)
├── tasks/
│   ├── build.yaml             # Build workflow (gen_userdata → diskimage_build)
│   ├── test.yaml              # Test workflow (run suite on guest)
│   └── run.yaml               # Interactive QEMU (SPICE display)
├── scripts/
│   ├── gen_userdata.py        # Generate cloud-init userdata
│   ├── diskimage_build.py     # Build disk image (download, provision, compact)
│   └── guest_run.py           # Start QEMU with SPICE display
├── rootfs/                    # Files baked into image via cloud-init write_files
│   ├── etc/                   # System config (SSH, systemd, udev rules)
│   ├── usr/local/bin/         # System scripts (automount, install-extras)
│   └── home/jellyfin/         # User scripts & config (Jellyfin launch, openbox)
├── auxiliary/
│   ├── cloudinit-base.user    # Base cloud-init config
│   ├── cloudinit-userdata.user # Generated userdata (DO NOT EDIT manually)
│   └── cloudinit-metadata.meta # Cloud-init metadata
├── tests/
│   └── test_appliance.py      # pytest tests (run on guest)
└── .claude/
    └── settings.local.json    # Claude Code project settings
```

## Configuration System

Configuration is **TOML-based** in `configs/*.toml`. Each variant (dk, us, etc.) has its own config file.

### Key Config Sections

**[jkab]** — Locale & internationalization
```toml
[jkab]
variant = "dk"
ui_culture = "da"              # Jellyfin UI language
metadata_country = "DK"        # Metadata region
metadata_language = "da"       # Metadata language
subtitle_language = "da"
audio_language = "da"
subtitle_mode = "Smart"
timezone = "Europe/Copenhagen" # Templated into cloud-init
```

**[cijoe.transport.qemu_guest]** — SSH access to guest
```toml
[cijoe.transport.qemu_guest]
username = "root"
password = "root"
hostname = "localhost"
port = 4200                    # SSH forwarded to 4200
```

**[qemu.guests.jkab-*]** — QEMU VM configuration
```toml
system_args.kwa = {cpu = "host", smp = 4, m = "4G", accel = "kvm"}
```

**[system-imaging.images.jkab-*]** — Cloud image + disk output paths
```toml
cloud.url = "https://cloud.debian.org/images/cloud/trixie/daily/latest/debian-13-generic-amd64-daily.qcow2"
disk.path = "~/system_imaging/disk/jkab-dk-x86_64.qcow2"
```

## Cloud-Init Provisioning

The appliance is provisioned by cloud-init via `auxiliary/cloudinit-userdata.user`.

### Main Provisions:
- **System**: openbox, X11, dbus, NetworkManager, hardware codecs
- **Jellyfin**: Server (with systemd service), Media Player client, ffmpeg7
- **CEC**: cec-utils, udev rules for Pulse-Eight CEC adapter
- **Media**: udisks2, NTFS/exFAT support, udev automount rules
- **Scripts**: jellyfin-start.sh, cec-jellyfin.sh, jkab-automount.sh
- **Boot**: Plymouth splash, quiet kernel, power button handling
- **Sample Media**: Sintel, Big Buck Bunny (Creative Commons test videos)

### First-Boot Setup:
1. Cloud-init runs provisioning (packages, scripts, config)
2. User logs in as `jellyfin` (auto-login on tty1)
3. startx launches openbox
4. openbox/autostart runs jellyfin-start.sh
5. jellyfin-start.sh launches Jellyfin Media Player
6. Server runs first-boot wizard (auto-configures user/libraries)

## Testing

Tests verify the provisioned image is correct **before deployment**.

### Run Tests
```bash
make test VARIANT=dk           # Runs on built image in QEMU guest
```

### Test Coverage (tests/test_appliance.py)
- **Packages**: jellyfin-media-player, jellyfin-server, openbox, cec-utils, etc.
- **Services**: jellyfin enabled/active, responds to HTTP API
- **Kiosk**: tty1 autologin, openbox setup, scripts executable
- **Locale**: /etc/jkab.conf generated with correct values
- **Config**: udev rules, logind power button, SSH config
- **First-Boot**: Wizard completion, user auth via API

Tests run via **cijoe testrunner** (pytest framework) with SSH access to guest.

## Key Scripts & Tools

### rootfs/home/jellyfin/bin/

**jellyfin-start.sh** — Launches Jellyfin Media Player
- Sets display, audio, GPU env vars
- Runs jkab-player.py (wraps jellyfin-media-player binary)

**cec-jellyfin.sh** — Translates CEC (TV remote) to keyboard events
- Uses cec-client to monitor remote commands
- Maps buttons to keys Jellyfin understands

**jkab-cec-bridge.py** — Legacy CEC bridge (disabled in favor of shell script)

**jkab-player.py** — Media player wrapper (custom launcher)

### rootfs/usr/local/bin/

**jkab-automount.sh** — udev hook for auto-mounting USB/SD media
- Triggered by udev event on device insertion
- Mounts to `/media/<label>`, triggers Jellyfin scan

**jkab-umount.sh** — udev hook for safe unmount

**jkab-install-extras.sh** — Optional: install diagnostic tools (intel-gpu-tools, vainfo, etc.)

## Development Workflow

### Adding a New File to Image
1. Place file in `rootfs/` with correct path/ownership/permissions
2. gen_userdata.py will pick it up as cloud-init write_files entry
3. Run `make build` (rebuilds userdata, provisions image)

### Modifying Cloud-Init Provisioning
1. Edit `auxiliary/cloudinit-base.user` (base YAML) or files in `rootfs/`
2. Run `make build`

### Creating a New Variant
1. Copy `configs/dk.toml` → `configs/us.toml`
2. Update `[jkab]` section (ui_culture, timezone, etc.)
3. Build: `make build VARIANT=us`

### Debugging on Booted Image
```bash
ssh -p 4200 root@localhost   # SSH to QEMU guest (test/interactive mode)
```

The guest runs network interface discovery via NetworkManager (SSH available).

## Build Output

### Artifacts
- **Disk Image**: `~/system_imaging/disk/jkab-dk-x86_64.qcow2` (main output)
- **SHA256**: `~/system_imaging/disk/jkab-dk-x86_64.qcow2.sha256`
- **Cloud Image Cache**: `~/system_imaging/cloud/debian-13-generic-amd64-daily.qcow2` (reused between builds)
- **Build Logs**: `cijoe-output/` (task outputs, SSH logs)

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
- **Jellyfin**: Media server + client (native Debian packages)
- **cec-utils**: HDMI CEC remote control bridge
- **PulseAudio**: Audio subsystem
- **intel-media-va-driver**: Hardware video decoding

## Related Resources

- **Jellyfin**: https://jellyfin.org/
- **cijoe**: https://github.com/refenv/cijoe
- **Cloud-Init**: https://cloudinit.readthedocs.io/
- **Debian Cloud Images**: https://cloud.debian.org/

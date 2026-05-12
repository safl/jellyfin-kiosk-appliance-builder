"""
Generate cloud-init user-data
==============================

Assembles cloud-init user-data by combining the base config with files from
the rootfs/ directory. Each file in rootfs/ becomes a write_files entry with
path, owner, permissions, and content derived from the actual file.

Reads [tellybox] config from cijoe to:
- Template __TELLYBOX_TIMEZONE__ in the base config
- Generate /etc/tellybox.conf with locale settings for build-time server setup

Retargetable: False
"""
import logging as log
import stat
from pathlib import Path


TELLYBOX_CONF_KEYS = [
    "variant",
    "ui_culture",
    "metadata_country",
    "metadata_language",
    "subtitle_language",
    "audio_language",
    "subtitle_mode",
]


def main(args, cijoe):
    repo_dir = Path.cwd()
    rootfs_dir = repo_dir / "rootfs"
    base_path = repo_dir / "auxiliary" / "cloudinit-base.user"
    output_path = repo_dir / "auxiliary" / "cloudinit-userdata.user"

    if not base_path.exists():
        log.error(f"Base config not found: {base_path}")
        return 1

    if not rootfs_dir.exists():
        log.error(f"rootfs directory not found: {rootfs_dir}")
        return 1

    tellybox = cijoe.getconf("tellybox", {})
    if not tellybox:
        log.error("No [tellybox] section found in config")
        return 1

    base = base_path.read_text(encoding="utf-8")

    # Template timezone
    timezone = tellybox.get("timezone", "UTC")
    base = base.replace("__TELLYBOX_TIMEZONE__", timezone)

    lines = [base, "", "write_files:"]

    for filepath in sorted(rootfs_dir.rglob("*")):
        if not filepath.is_file():
            continue

        target = "/" + str(filepath.relative_to(rootfs_dir))
        content = filepath.read_text(encoding="utf-8")
        mode = stat.S_IMODE(filepath.stat().st_mode)
        perms = f"0{mode:o}"

        if target.startswith("/home/tellybox/"):
            owner = "tellybox:tellybox"
            defer = True
        else:
            owner = "root:root"
            defer = False

        lines.append(f"  - path: {target}")
        lines.append(f"    owner: {owner}")
        lines.append(f'    permissions: "{perms}"')
        if defer:
            lines.append("    defer: true")
        lines.append("    content: |")
        for line in content.splitlines():
            lines.append(f"      {line}")
        lines.append("")

    # Generate /etc/tellybox.conf from [tellybox] config
    lines.append("  - path: /etc/tellybox.conf")
    lines.append("    owner: root:root")
    lines.append('    permissions: "0644"')
    lines.append("    content: |")
    for key in TELLYBOX_CONF_KEYS:
        value = tellybox.get(key, "")
        lines.append(f'      TELLYBOX_{key.upper()}="{value}"')
    lines.append("")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info(f"Generated {output_path}")

    return 0

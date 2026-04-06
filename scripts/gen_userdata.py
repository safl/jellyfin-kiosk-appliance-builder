"""
Generate cloud-init user-data
==============================

Assembles cloud-init user-data by combining the base config with files from
the rootfs/ directory. Each file in rootfs/ becomes a write_files entry with
path, owner, permissions, and content derived from the actual file.

Reads [jkab] config from cijoe to:
- Template __JKAB_TIMEZONE__ in the base config
- Generate /etc/jkab.conf with locale settings for build-time server setup

Retargetable: False
"""
import logging as log
import stat
from pathlib import Path


JKAB_CONF_KEYS = [
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

    jkab = cijoe.getconf("jkab", {})
    if not jkab:
        log.error("No [jkab] section found in config")
        return 1

    base = base_path.read_text()

    # Template timezone
    timezone = jkab.get("timezone", "UTC")
    base = base.replace("__JKAB_TIMEZONE__", timezone)

    lines = [base, "", "write_files:"]

    for filepath in sorted(rootfs_dir.rglob("*")):
        if not filepath.is_file():
            continue

        target = "/" + str(filepath.relative_to(rootfs_dir))
        content = filepath.read_text()
        mode = stat.S_IMODE(filepath.stat().st_mode)
        perms = f"0{mode:o}"

        if target.startswith("/home/jellyfin/"):
            owner = "jellyfin:jellyfin"
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

    # Generate /etc/jkab.conf from [jkab] config
    lines.append("  - path: /etc/jkab.conf")
    lines.append("    owner: root:root")
    lines.append('    permissions: "0644"')
    lines.append("    content: |")
    for key in JKAB_CONF_KEYS:
        value = jkab.get(key, "")
        lines.append(f'      JKAB_{key.upper()}="{value}"')
    lines.append("")

    output_path.write_text("\n".join(lines) + "\n")
    log.info(f"Generated {output_path}")

    return 0

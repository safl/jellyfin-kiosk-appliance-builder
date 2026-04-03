"""
Generate cloud-init user-data
==============================

Assembles cloud-init user-data by combining the base config with files from
the rootfs/ directory. Each file in rootfs/ becomes a write_files entry with
path, owner, permissions, and content derived from the actual file.

Retargetable: False
"""
import logging as log
import stat
from pathlib import Path


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

    base = base_path.read_text()

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

    output_path.write_text("\n".join(lines) + "\n")
    log.info(f"Generated {output_path}")

    return 0

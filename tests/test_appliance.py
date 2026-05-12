"""
Tellybox Appliance Tests
====================

Verify the baked appliance image has all packages, services, config files,
and first-boot setup working correctly. Run via cijoe testrunner on a
booted QEMU guest with SSH access.

Usage:
    cijoe tasks/test.yaml --monitor -c configs/dk.toml
"""
from cijoe.core.command import Cijoe


# --- Packages ---


def test_python3_installed(cijoe: Cijoe):
    err, state = cijoe.run("dpkg -l python3")
    assert not err, state.output()


def test_python3_pygame_installed(cijoe: Cijoe):
    err, state = cijoe.run("python3 -c 'import pygame; print(pygame.__version__)'")
    assert not err, state.output()


def test_python3_flask_installed(cijoe: Cijoe):
    err, state = cijoe.run("python3 -c 'import flask; print(flask.__version__)'")
    assert not err, state.output()


def test_python3_cec_installed(cijoe: Cijoe):
    """The libcec Python binding is required by the CEC bridge."""
    err, state = cijoe.run("python3 -c 'import cec'")
    assert not err, state.output()


def test_mpv_installed(cijoe: Cijoe):
    err, state = cijoe.run("which mpv")
    assert not err, state.output()


def test_pipewire_audio_installed(cijoe: Cijoe):
    """PipeWire + WirePlumber are required so mpv routes to HDMI by default."""
    err, state = cijoe.run("dpkg -l pipewire-audio wireplumber pulseaudio-utils")
    assert not err, state.output()


def test_openbox_installed(cijoe: Cijoe):
    err, state = cijoe.run("dpkg -l openbox")
    assert not err, state.output()


def test_xdotool_installed(cijoe: Cijoe):
    err, state = cijoe.run("which xdotool")
    assert not err, state.output()


def test_unclutter_installed(cijoe: Cijoe):
    err, state = cijoe.run("dpkg -l unclutter")
    assert not err, state.output()


def test_cec_utils_installed(cijoe: Cijoe):
    err, state = cijoe.run("dpkg -l cec-utils")
    assert not err, state.output()


def test_udisks2_installed(cijoe: Cijoe):
    err, state = cijoe.run("dpkg -l udisks2")
    assert not err, state.output()


# --- Services ---


def test_tellybox_server_service_enabled(cijoe: Cijoe):
    err, state = cijoe.run("systemctl is-enabled tellybox-server")
    assert not err
    assert "enabled" in state.output()


def test_tellybox_server_service_active(cijoe: Cijoe):
    err, state = cijoe.run("systemctl is-active tellybox-server")
    assert not err
    assert "active" in state.output()


def test_tellybox_server_responds(cijoe: Cijoe):
    """Wait up to 30s for tellybox-server to be ready, then check health endpoint."""
    err, state = cijoe.run(
        "for i in $(seq 1 15); do"
        " curl -sf http://localhost:8080/api/health >/dev/null 2>&1 && break;"
        " sleep 2; done;"
        " curl -sf http://localhost:8080/api/health"
    )
    assert not err, "tellybox-server not responding after 30s"
    assert "ok" in state.output()


# --- Kiosk ---


def test_getty_autologin(cijoe: Cijoe):
    err, state = cijoe.run(
        "cat /etc/systemd/system/getty@tty1.service.d/autologin.conf"
    )
    assert not err
    assert "--autologin tellybox" in state.output()


def test_bash_profile(cijoe: Cijoe):
    err, state = cijoe.run("cat /home/tellybox/.bash_profile")
    assert not err
    assert "startx" in state.output()


def test_xinitrc(cijoe: Cijoe):
    err, state = cijoe.run("cat /home/tellybox/.xinitrc")
    assert not err
    assert "openbox-session" in state.output()


def test_openbox_autostart(cijoe: Cijoe):
    err, state = cijoe.run("cat /home/tellybox/.config/openbox/autostart")
    assert not err
    output = state.output()
    assert "tellybox-player.py" in output
    assert "tellybox-cec-bridge.py" in output
    assert "unclutter" in output
    assert "xset s off" in output


# --- Locale ---


def test_tellybox_conf_exists(cijoe: Cijoe):
    err, state = cijoe.run("cat /etc/tellybox.conf")
    assert not err
    output = state.output()
    assert "TELLYBOX_VARIANT=" in output
    assert "TELLYBOX_UI_CULTURE=" in output
    assert "TELLYBOX_METADATA_COUNTRY=" in output
    assert "TELLYBOX_METADATA_LANGUAGE=" in output
    assert "TELLYBOX_SUBTITLE_LANGUAGE=" in output
    assert "TELLYBOX_AUDIO_LANGUAGE=" in output
    assert "TELLYBOX_SUBTITLE_MODE=" in output


def test_tellybox_conf_matches_config(cijoe: Cijoe):
    variant = cijoe.getconf("tellybox.variant")
    assert variant, "No tellybox.variant in config"

    err, state = cijoe.run("cat /etc/tellybox.conf")
    assert not err
    assert f'TELLYBOX_VARIANT="{variant}"' in state.output()


# --- Config files ---


def test_udev_cec_rules(cijoe: Cijoe):
    err, state = cijoe.run("cat /etc/udev/rules.d/99-pulse-eight-cec.rules")
    assert not err
    assert "2548" in state.output()


def test_udev_automount_rules(cijoe: Cijoe):
    err, state = cijoe.run("cat /etc/udev/rules.d/90-automount-media.rules")
    assert not err
    assert "tellybox-automount.sh" in state.output()


def test_logind_power_button(cijoe: Cijoe):
    err, state = cijoe.run(
        "cat /etc/systemd/logind.conf.d/90-power-button.conf"
    )
    assert not err
    assert "HandlePowerKey=poweroff" in state.output()


def test_scripts_executable(cijoe: Cijoe):
    scripts = [
        "/home/tellybox/bin/tellybox-player.py",
        "/home/tellybox/bin/tellybox-cec-bridge.py",
        "/usr/local/bin/tellybox-server.py",
        "/usr/local/bin/tellybox-automount.sh",
        "/usr/local/bin/tellybox-umount.sh",
        "/usr/local/bin/tellybox-install-extras.sh",
    ]
    for script in scripts:
        err, state = cijoe.run(f"test -x {script}")
        assert not err, f"{script} is not executable"


# --- Media directories ---


def test_media_root_exists(cijoe: Cijoe):
    """/media is the mount point for user-supplied drives."""
    err, state = cijoe.run("test -d /media")
    assert not err, "/media does not exist"


def test_indexer_root_empty_with_no_drives(cijoe: Cijoe):
    """With no drives plugged in, the Media Library has no Collections."""
    err, state = cijoe.run("curl -sf http://localhost:8080/api/media")
    assert not err, "indexer root failed"
    assert '"items": []' in state.output() or '"items":[]' in state.output()


def test_tellybox_cache_directory(cijoe: Cijoe):
    """Verify cache directory for tellybox-server progress tracking."""
    err, state = cijoe.run("test -d /home/tellybox/.cache/tellybox")
    assert not err, "/home/tellybox/.cache/tellybox does not exist"


# --- Plymouth ---


def test_grub_quiet_splash(cijoe: Cijoe):
    err, state = cijoe.run("grep GRUB_CMDLINE_LINUX_DEFAULT /etc/default/grub")
    assert not err
    assert "quiet splash" in state.output()


def test_grub_no_earlyprintk(cijoe: Cijoe):
    err, state = cijoe.run("grep GRUB_CMDLINE_LINUX= /etc/default/grub")
    assert not err
    assert "earlyprintk" not in state.output()


# --- Cloud-init ---


def test_cloud_init_disabled_after_provisioning(cijoe: Cijoe):
    """The baked image must have cloud-init disabled so it doesn't re-run
    provisioning (re-installing packages, resetting state) on every boot."""
    err, _ = cijoe.run("test -e /etc/cloud/cloud-init.disabled")
    assert not err, "/etc/cloud/cloud-init.disabled is missing"


def test_cache_dir_owned_by_tellybox(cijoe: Cijoe):
    """The progress-tracking cache must be writable by the tellybox-server
    process, which runs as user `tellybox`. If cloud-init creates it as root
    (the default if mkdir happens after the home-dir chown sweep), the server
    silently fails to save watch progress."""
    err, state = cijoe.run("stat -c '%U' /home/tellybox/.cache/tellybox")
    assert not err
    assert state.output().strip() == "tellybox"

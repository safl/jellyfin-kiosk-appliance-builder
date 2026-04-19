"""
JKAB Appliance Tests
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


def test_jkab_server_service_enabled(cijoe: Cijoe):
    err, state = cijoe.run("systemctl is-enabled jkab-server")
    assert not err
    assert "enabled" in state.output()


def test_jkab_server_service_active(cijoe: Cijoe):
    err, state = cijoe.run("systemctl is-active jkab-server")
    assert not err
    assert "active" in state.output()


def test_jkab_server_responds(cijoe: Cijoe):
    """Wait up to 30s for jkab-server to be ready, then check health endpoint."""
    err, state = cijoe.run(
        "for i in $(seq 1 15); do"
        " curl -sf http://localhost:8080/api/health >/dev/null 2>&1 && break;"
        " sleep 2; done;"
        " curl -sf http://localhost:8080/api/health"
    )
    assert not err, "jkab-server not responding after 30s"
    assert "ok" in state.output()


# --- Kiosk ---


def test_getty_autologin(cijoe: Cijoe):
    err, state = cijoe.run(
        "cat /etc/systemd/system/getty@tty1.service.d/autologin.conf"
    )
    assert not err
    assert "--autologin jkab" in state.output()


def test_bash_profile(cijoe: Cijoe):
    err, state = cijoe.run("cat /home/jkab/.bash_profile")
    assert not err
    assert "startx" in state.output()


def test_xinitrc(cijoe: Cijoe):
    err, state = cijoe.run("cat /home/jkab/.xinitrc")
    assert not err
    assert "openbox-session" in state.output()


def test_openbox_autostart(cijoe: Cijoe):
    err, state = cijoe.run("cat /home/jkab/.config/openbox/autostart")
    assert not err
    output = state.output()
    assert "jkab-player.py" in output
    assert "jkab-cec-bridge.py" in output
    assert "unclutter" in output
    assert "xset s off" in output


# --- Locale ---


def test_jkab_conf_exists(cijoe: Cijoe):
    err, state = cijoe.run("cat /etc/jkab.conf")
    assert not err
    output = state.output()
    assert "JKAB_VARIANT=" in output
    assert "JKAB_UI_CULTURE=" in output
    assert "JKAB_METADATA_COUNTRY=" in output
    assert "JKAB_METADATA_LANGUAGE=" in output
    assert "JKAB_SUBTITLE_LANGUAGE=" in output
    assert "JKAB_AUDIO_LANGUAGE=" in output
    assert "JKAB_SUBTITLE_MODE=" in output


def test_jkab_conf_matches_config(cijoe: Cijoe):
    variant = cijoe.getconf("jkab.variant")
    assert variant, "No jkab.variant in config"

    err, state = cijoe.run("cat /etc/jkab.conf")
    assert not err
    assert f'JKAB_VARIANT="{variant}"' in state.output()


# --- Config files ---


def test_udev_cec_rules(cijoe: Cijoe):
    err, state = cijoe.run("cat /etc/udev/rules.d/99-pulse-eight-cec.rules")
    assert not err
    assert "2548" in state.output()


def test_udev_automount_rules(cijoe: Cijoe):
    err, state = cijoe.run("cat /etc/udev/rules.d/90-automount-media.rules")
    assert not err
    assert "jkab-automount.sh" in state.output()


def test_logind_power_button(cijoe: Cijoe):
    err, state = cijoe.run(
        "cat /etc/systemd/logind.conf.d/90-power-button.conf"
    )
    assert not err
    assert "HandlePowerKey=poweroff" in state.output()


def test_scripts_executable(cijoe: Cijoe):
    scripts = [
        "/home/jkab/bin/jkab-player.py",
        "/home/jkab/bin/jkab-cec-bridge.py",
        "/usr/local/bin/jkab-server.py",
        "/usr/local/bin/jkab-automount.sh",
        "/usr/local/bin/jkab-umount.sh",
        "/usr/local/bin/jkab-install-extras.sh",
    ]
    for script in scripts:
        err, state = cijoe.run(f"test -x {script}")
        assert not err, f"{script} is not executable"


# --- Media directories ---


def test_media_directories_exist(cijoe: Cijoe):
    """Verify /media root and built-in 'sample' drive layout."""
    for directory in ["/media", "/media/sample", "/media/sample/Movies"]:
        err, state = cijoe.run(f"test -d {directory}")
        assert not err, f"{directory} does not exist"


def test_sample_media_present(cijoe: Cijoe):
    """At least one sample video should land in /media/sample/Movies."""
    err, state = cijoe.run(
        "ls /media/sample/Movies/ | grep -E '\\.(mp4|mkv)$'"
    )
    assert not err, "no sample videos found in /media/sample/Movies"


def test_indexer_root_returns_categories(cijoe: Cijoe):
    """Root API exposes Movies and Shows virtual categories."""
    err, state = cijoe.run("curl -sf http://localhost:8080/api/media")
    assert not err, "indexer root failed"
    output = state.output()
    assert '"name": "Movies"' in output or '"name":"Movies"' in output
    assert '"name": "Shows"' in output or '"name":"Shows"' in output


def test_indexer_movies_category_finds_samples(cijoe: Cijoe):
    """Movies category should aggregate sample/Movies contents."""
    err, state = cijoe.run("curl -sf http://localhost:8080/api/media/Movies")
    assert not err, "indexer Movies failed"
    output = state.output()
    assert "sample/Movies" in output, "sample movies not surfaced via Movies category"


def test_jkab_cache_directory(cijoe: Cijoe):
    """Verify cache directory for jkab-server progress tracking."""
    err, state = cijoe.run("test -d /home/jkab/.cache/jkab")
    assert not err, "/home/jkab/.cache/jkab does not exist"


# --- Plymouth ---


def test_grub_quiet_splash(cijoe: Cijoe):
    err, state = cijoe.run("grep GRUB_CMDLINE_LINUX_DEFAULT /etc/default/grub")
    assert not err
    assert "quiet splash" in state.output()


def test_grub_no_earlyprintk(cijoe: Cijoe):
    err, state = cijoe.run("grep GRUB_CMDLINE_LINUX= /etc/default/grub")
    assert not err
    assert "earlyprintk" not in state.output()

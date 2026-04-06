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


def test_jellyfin_media_player_installed(cijoe: Cijoe):
    err, state = cijoe.run("dpkg -l jellyfin-media-player")
    assert not err, state.output()


def test_jellyfin_server_installed(cijoe: Cijoe):
    err, state = cijoe.run("dpkg -l jellyfin-server")
    assert not err, state.output()


def test_jellyfin_ffmpeg_installed(cijoe: Cijoe):
    err, state = cijoe.run("dpkg -l jellyfin-ffmpeg7")
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


def test_jellyfin_service_enabled(cijoe: Cijoe):
    err, state = cijoe.run("systemctl is-enabled jellyfin")
    assert not err
    assert "enabled" in state.output()


def test_jellyfin_service_active(cijoe: Cijoe):
    err, state = cijoe.run("systemctl is-active jellyfin")
    assert not err
    assert "active" in state.output()


def test_jellyfin_server_responds(cijoe: Cijoe):
    """Wait up to 60s for server API to be ready, then check response."""
    err, state = cijoe.run(
        "for i in $(seq 1 30); do"
        " curl -sf http://localhost:8096/System/Info/Public >/dev/null 2>&1 && break;"
        " sleep 2; done;"
        " curl -sf http://localhost:8096/System/Info/Public"
    )
    assert not err, "Jellyfin server not responding after 60s"
    assert "Version" in state.output()


# --- Kiosk ---


def test_getty_autologin(cijoe: Cijoe):
    err, state = cijoe.run(
        "cat /etc/systemd/system/getty@tty1.service.d/autologin.conf"
    )
    assert not err
    assert "--autologin jellyfin" in state.output()


def test_bash_profile(cijoe: Cijoe):
    err, state = cijoe.run("cat /home/jellyfin/.bash_profile")
    assert not err
    assert "startx" in state.output()


def test_xinitrc(cijoe: Cijoe):
    err, state = cijoe.run("cat /home/jellyfin/.xinitrc")
    assert not err
    assert "openbox-session" in state.output()


def test_openbox_autostart(cijoe: Cijoe):
    err, state = cijoe.run("cat /home/jellyfin/.config/openbox/autostart")
    assert not err
    assert "jellyfin-start.sh" in state.output()
    assert "cec-jellyfin.sh" in state.output()
    assert "unclutter" in state.output()
    assert "xset s off" in state.output()


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
        "/home/jellyfin/bin/jellyfin-start.sh",
        "/home/jellyfin/bin/cec-jellyfin.sh",
        "/usr/local/bin/jkab-automount.sh",
        "/usr/local/bin/jkab-umount.sh",
        "/usr/local/bin/jkab-install-extras.sh",
    ]
    for script in scripts:
        err, state = cijoe.run(f"test -x {script}")
        assert not err, f"{script} is not executable"


# --- Server setup ---


def test_wizard_completed(cijoe: Cijoe):
    """Wait up to 90s for the first-boot setup to complete."""
    err, state = cijoe.run(
        "for i in $(seq 1 45); do"
        " curl -sf http://localhost:8096/System/Info/Public 2>/dev/null"
        " | python3 -c \"import sys,json; d=json.load(sys.stdin);"
        " assert d['StartupWizardCompleted']\" 2>/dev/null && break;"
        " sleep 2; done;"
        " curl -sf http://localhost:8096/System/Info/Public"
        " | python3 -c \"import sys,json; d=json.load(sys.stdin);"
        " assert d['StartupWizardCompleted'], 'Wizard not completed'\""
    )
    assert not err, "Startup wizard not completed after 90s"


def test_jellyfin_user_auth(cijoe: Cijoe):
    err, state = cijoe.run(
        "curl -sf -X POST http://localhost:8096/Users/AuthenticateByName"
        " -H 'Content-Type: application/json'"
        " -H 'Authorization: MediaBrowser Client=\"JKAB\", Device=\"JKAB\","
        " DeviceId=\"jkab\", Version=\"1.0\"'"
        " -d '{\"Username\":\"jellyfin\",\"Pw\":\"jellyfin\"}'"
        " | python3 -c \"import sys,json; d=json.load(sys.stdin);"
        " print(d['User']['Name'])\""
    )
    assert not err, "Failed to authenticate as jellyfin"
    assert "jellyfin" in state.output()


# --- Plymouth ---


def test_grub_quiet_splash(cijoe: Cijoe):
    err, state = cijoe.run("grep GRUB_CMDLINE_LINUX_DEFAULT /etc/default/grub")
    assert not err
    assert "quiet splash" in state.output()


def test_grub_no_earlyprintk(cijoe: Cijoe):
    err, state = cijoe.run("grep GRUB_CMDLINE_LINUX= /etc/default/grub")
    assert not err
    assert "earlyprintk" not in state.output()

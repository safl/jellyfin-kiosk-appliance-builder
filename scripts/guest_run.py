"""
Run a qemu guest with display
==============================

Starts the guest with a SPICE display on port 5930. Connect with
a SPICE viewer (e.g. remote-viewer spice://localhost:5930).

Retargetable: False
"""
import logging as log
from argparse import ArgumentParser

from cijoe.qemu.wrapper import Guest


def add_args(parser: ArgumentParser):
    parser.add_argument("--guest_name", type=str, required=True)


def main(args, cijoe):
    guest = Guest(cijoe, cijoe.config, args.guest_name)

    display_args = [
        "-vga", "virtio",
        "-spice", "port=5930,disable-ticketing=on",
    ]

    log.info("SPICE display available at spice://localhost:5930")

    err = guest.start(daemonize=False, extra_args=display_args)
    if err:
        log.error(f"guest.start() : err({err})")
        return err

    return 0

#!/usr/bin/env python3
"""Validate and install a matching Advantage360 Pro UF2 pair on macOS."""

from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import re
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


BLOCK_SIZE = 512
PAYLOAD_SIZE = 256
APP_START, APP_END = 0x26000, 0xEC000
MAX_UF2_SIZE = 2 * 1024 * 1024  # nRF52840 has 1 MiB of flash.
PRODUCTS = {"left": b"Adv360 Pro", "right": b"Adv360 Pro rt"}
HOTKEYS = {"left": "Mod + Hotkey 1", "right": "Mod + Hotkey 3"}
FILE_PATTERN = re.compile(r"(?:(.+)-)?(left|right)(-clique)?\.uf2", re.IGNORECASE)


class FlashError(Exception):
    pass


@dataclass(frozen=True)
class Firmware:
    path: Path
    side: str
    data: bytes


@dataclass(frozen=True)
class BootDisk:
    identifier: str
    mount: Path
    side: str | None


def uf2_blocks(image, expected_family=0xADA52840):
    if not image or len(image) > MAX_UF2_SIZE or len(image) % BLOCK_SIZE:
        raise FlashError("UF2 size must be a nonzero multiple of 512 bytes within device capacity")
    block_count = len(image) // BLOCK_SIZE
    for index, offset in enumerate(range(0, len(image), BLOCK_SIZE)):
        first, second, flags, address, size, number, total, family = struct.unpack_from(
            "<8I", image, offset
        )
        end_magic, = struct.unpack_from("<I", image, offset + 508)
        if (first, second, end_magic) != (0x0A324655, 0x9E5D5157, 0x0AB16F30):
            raise FlashError(f"Invalid UF2 magic in block {index}")
        if ((flags, size, number, total) != (0x2000, PAYLOAD_SIZE, index, block_count)
                or (expected_family is not None and family != expected_family)):
            raise FlashError(f"Block {index} is not a sequential nRF52840 UF2 block")
        yield address, image[offset + 32:offset + 32 + size]


def application_payload(image):
    payload = []
    for index, (address, data) in enumerate(uf2_blocks(image)):
        if address != APP_START + index * PAYLOAD_SIZE or address + len(data) > APP_END:
            raise FlashError(f"Block at 0x{address:x} is outside the expected application image")
        payload.append(data)
    return b"".join(payload)


def firmware_side(payload, *, readback=False):
    # This Zephyr version stores ASCII USB string descriptors before expanding them to UTF-16.
    matches = []
    for side, name in PRODUCTS.items():
        descriptor = bytes([2 * len(name) + 2, 3]) + name + b"\0"
        offset = payload.find(descriptor)
        if offset >= 0:
            matches.append((offset, side))
    if not matches:
        return None
    if readback:
        # CURRENT.UF2 includes flash beyond the active image. A previously
        # installed, larger image can leave another descriptor in that tail.
        return min(matches)[1]
    return matches[0][1] if len(matches) == 1 else None


def read_pair(left, right):
    names = FILE_PATTERN.fullmatch(left.name), FILE_PATTERN.fullmatch(right.name)
    if (any(not name for name in names) or names[0][2].lower() != "left"
            or names[1][2].lower() != "right"
            or (names[0][1], names[0][3]) != (names[1][1], names[1][3])):
        raise FlashError("Provide left and right UF2 files in that order with the same build prefix and variant")
    images = []
    for path, side in zip((left, right), ("left", "right")):
        with path.open("rb") as source:
            image = source.read(MAX_UF2_SIZE + 1)
        if firmware_side(application_payload(image)) != side:
            raise FlashError(f"{path}: expected the USB descriptor of the {side} module")
        images.append(Firmware(path, side, image))
    return images


def diskutil(*args):
    return plistlib.loads(subprocess.check_output(["/usr/sbin/diskutil", *args], timeout=10))


def read_current(mount):
    with (mount / "CURRENT.UF2").open("rb") as current:
        image = current.read(MAX_UF2_SIZE + 1)
    # Adafruit's readback sets its board-specific application family ID.
    payload = []
    for address, data in uf2_blocks(image, expected_family=None):
        if APP_START <= address < APP_END:
            if address != APP_START + len(payload) * PAYLOAD_SIZE:
                raise FlashError("CURRENT.UF2 has a gap in the application region")
            payload.append(data)
    return b"".join(payload)


def installed_side(mount):
    try:
        return firmware_side(read_current(mount), readback=True)
    except (OSError, FlashError):
        return None


def boot_disks(identify=True):
    result = []
    for identifier in diskutil("list", "-plist", "external", "physical").get("AllDisks", []):
        try:
            info = diskutil("info", "-plist", identifier)
        except subprocess.CalledProcessError:
            continue  # The device may have disappeared between the two calls.
        label = re.sub(r"[^a-z0-9]", "", info.get("VolumeName", "").lower())
        if label != "adv360pro" or info.get("BusProtocol") != "USB" or info.get("Internal") is not False:
            continue
        if not info.get("MountPoint"):
            continue
        mount = Path(info["MountPoint"])
        with (mount / "INFO_UF2.TXT").open("rb") as marker:
            if b"UF2 Bootloader" not in marker.read(4096):
                raise FlashError(f"{mount}: unrecognized UF2 bootloader metadata")
        result.append(BootDisk(identifier, mount, installed_side(mount) if identify else None))
    return result


def wait_for_disk(side, timeout, allow_unidentified):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        disks = boot_disks()
        if len(disks) > 1:
            raise FlashError("More than one Adv360 Pro bootloader is mounted. Exit both and restart")
        if disks:
            disk = disks[0]
            if disk.side and disk.side != side:
                raise FlashError(f"Expected {side}, but the mounted module runs {disk.side} firmware")
            if not disk.side and not allow_unidentified:
                raise FlashError("CURRENT.UF2 did not identify the module. See docs/flash-macos.md")
            return disk
        time.sleep(0.5)
    raise FlashError(f"Timed out waiting for the {side} module ({HOTKEYS[side]})")


def write_image(image, disk):
    # A directory descriptor keeps the write tied to this mount if a disk disappears.
    directory = os.open(disk.mount, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if (os.fstat(directory).st_dev == disk.mount.parent.stat().st_dev
                or boot_disks() != [disk]):
            raise FlashError("The sole bootloader mount changed before the write")
        filename = "ADV360L.UF2" if image.side == "left" else "ADV360R.UF2"
        target = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644, dir_fd=directory)
        written = 0
        sync_error = None
        try:
            view = memoryview(image.data)
            while written < len(view):
                count = os.write(target, view[written:])
                if not count:
                    raise FlashError(f"USB write stopped after {written} bytes")
                written += count
            try:
                os.fsync(target)
            except OSError as error:
                sync_error = error
        finally:
            os.close(target)
        return sync_error
    finally:
        os.close(directory)


def flash(image, timeout, allow_unidentified):
    if boot_disks(identify=False):
        raise FlashError("Start this step with both modules out of bootloader mode")
    print(f"[{image.side}] Press {HOTKEYS[image.side]} now. Waiting for its USB drive…", flush=True)
    disk = wait_for_disk(image.side, timeout, allow_unidentified)
    print(f"[{image.side}] Copying {image.path.name} to {disk.mount} ({disk.identifier})", flush=True)
    sync_error = write_image(image, disk)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        disks = boot_disks(identify=False)
        if not disks:
            if sync_error:
                raise FlashError(f"{image.side} volume disconnected after a sync error ({sync_error}). "
                                 "Verify the installed firmware before continuing")
            print(f"[{image.side}] Bootloader volume disappeared. Check that its LEDs stop flashing blue.")
            return
        if len(disks) != 1 or disks[0].identifier != disk.identifier:
            raise FlashError("Bootloader inventory changed during the update")
        time.sleep(0.5)
    raise FlashError(f"The {image.side} bootloader did not disconnect after the copy. Check the module")


def verify_installed(images):
    disks = boot_disks(identify=False)
    if len(disks) != 1:
        raise FlashError("Open exactly one bootloader volume to verify its installed firmware")
    installed = read_current(disks[0].mount)
    for image in images:
        if installed.startswith(application_payload(image.data)):
            print(f"[{image.side}] Installed bytes match {image.path.name}")
            return
    raise FlashError("CURRENT.UF2 does not match the supplied pair")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="validate both UF2 files and print hashes")
    modes.add_argument("--list", action="store_true", help="list mounted Adv360 Pro bootloader volumes")
    modes.add_argument("--verify-installed", action="store_true",
                       help="compare one open bootloader's CURRENT.UF2 with the supplied pair")
    modes.add_argument("--right-only", action="store_true", help="resume after the left module was updated")
    parser.add_argument("--timeout", default=120, type=int, help="seconds to wait for each USB event (default: 120)")
    parser.add_argument("--allow-unidentified", action="store_true",
                        help="trust the requested physical hotkey when CURRENT.UF2 cannot identify a module")
    parser.add_argument("firmware", metavar="UF2", nargs="*", type=Path)
    args = parser.parse_args()
    if len(args.firmware) != (0 if args.list else 2) or args.timeout < 1:
        parser.error("use --list, or supply the left UF2 followed by the right UF2 and a positive timeout")
    try:
        if args.list:
            disks = boot_disks()
            for disk in disks:
                print(f"{disk.identifier}\t{disk.mount}\t{disk.side or 'unidentified'}")
            if not disks:
                print("No Adv360 Pro bootloader volumes mounted.")
            return 0

        images = read_pair(*args.firmware)
        for image in images:
            print(f"{hashlib.sha256(image.data).hexdigest()}  {image.path}")
        if args.dry_run:
            return 0
        if args.verify_installed:
            verify_installed(images)
            return 0

        print("Connect both modules by data USB and keep the left module powered on.")
        for image in images[1:] if args.right_only else images:
            flash(image, args.timeout, args.allow_unidentified)
            if image.side == "left":
                print("Wait for the right module to reconnect to the left before using the next hotkey.")
        print("Test typing from both modules. If the right LEDs flash red, power-cycle left first, then right.")
        return 0
    except (FlashError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Adv360 flash: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped. Check which module updated before restarting.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

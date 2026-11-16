import importlib.util
import io
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("flash_adv360", ROOT / "bin/flash_adv360.py")
flash = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = flash
spec.loader.exec_module(flash)


def uf2(product, address=0x26000, family=0xADA52840):
    # USB product string as emitted by this board's Zephyr USB descriptor table.
    payload = bytes([len(product) * 2 + 2, 3]) + product.encode() + b"\0"
    header = struct.pack("<8I", 0x0A324655, 0x9E5D5157, 0x2000,
                         address, 256, 0, 1, family)
    return (header + payload).ljust(508, b"\0") + struct.pack("<I", 0x0AB16F30)


class FlashTest(unittest.TestCase):
    def test_identifies_active_firmware_with_stale_descriptor_in_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            mount = Path(folder)
            image = bytearray(uf2("Adv360 Pro rt"))
            stale_tail = b"\x16\x03Adv360 Pro\0"
            image[120:120 + len(stale_tail)] = stale_tail
            (mount / "CURRENT.UF2").write_bytes(image)
            self.assertEqual(flash.installed_side(mount), "right")
            self.assertIsNone(flash.firmware_side(flash.application_payload(image)))

    def test_refuses_renamed_wrong_half_and_settings_erase(self):
        with tempfile.TemporaryDirectory() as folder:
            left = Path(folder) / "build-left.uf2"
            right = Path(folder) / "build-right.uf2"
            right.write_bytes(uf2("Adv360 Pro rt"))
            for wrong in (uf2("Adv360 Pro rt"), (ROOT / "settings-reset.uf2").read_bytes()):
                with self.subTest(wrong_hash=hash(wrong)):
                    left.write_bytes(wrong)
                    with self.assertRaises(flash.FlashError):
                        flash.read_pair(left, right)
            left.write_bytes(uf2("Adv360 Pro"))
            self.assertEqual([image.side for image in flash.read_pair(left, right)],
                             ["left", "right"])

    def test_refuses_truncation_or_out_of_partition(self):
        for wrong in (uf2("Adv360 Pro")[:-1], uf2("Adv360 Pro", 0xEC000)):
            with self.assertRaises(flash.FlashError):
                flash.application_payload(wrong)

    def test_refuses_ambiguous_disks_and_wrong_destination(self):
        left_disk = flash.BootDisk("disk8", Path("/Volumes/Adv360 Pro"), "left")
        right_disk = flash.BootDisk("disk9", Path("/Volumes/Adv360 Pro 1"), "right")
        with patch.object(flash, "boot_disks", return_value=[left_disk, right_disk]):
            with self.assertRaises(flash.FlashError):
                flash.wait_for_disk("left", 1, False)
        with patch.object(flash, "boot_disks", return_value=[right_disk]):
            with self.assertRaises(flash.FlashError):
                flash.wait_for_disk("left", 1, True)

    def test_current_uf2_identifies_a_renamed_mount(self):
        with tempfile.TemporaryDirectory() as folder:
            mount = Path(folder)
            (mount / "INFO_UF2.TXT").write_text("UF2 Bootloader v1.0\nModel: Adv360 Pro\n")
            # Readback can use the board's family ID instead of generic nRF52840.
            (mount / "CURRENT.UF2").write_bytes(uf2("Adv360 Pro rt", family=0x12345678))
            inventory = {"AllDisks": ["disk9"]}
            info = {"BusProtocol": "USB", "Internal": False, "MountPoint": str(mount),
                    "VolumeName": "ADV360PRO"}
            with patch.object(flash, "diskutil", side_effect=[inventory, info]):
                self.assertEqual(flash.boot_disks(), [flash.BootDisk("disk9", mount, "right")])

    def test_readback_requires_matching_bytes_not_just_the_right_role(self):
        with tempfile.TemporaryDirectory() as folder:
            mount = Path(folder)
            image = flash.Firmware(Path("build-left.uf2"), "left", uf2("Adv360 Pro"))
            (mount / "CURRENT.UF2").write_bytes(image.data)
            with patch.object(flash, "boot_disks", return_value=[flash.BootDisk("disk8", mount, None)]):
                with redirect_stdout(io.StringIO()):
                    flash.verify_installed([image])
                different = bytearray(image.data)
                different[200] = 1
                (mount / "CURRENT.UF2").write_bytes(different)
                with self.assertRaises(flash.FlashError):
                    flash.verify_installed([image])


if __name__ == "__main__":
    unittest.main()

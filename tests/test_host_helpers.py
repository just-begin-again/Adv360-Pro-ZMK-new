import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "host" / "helpers"


class HostHelperTests(unittest.TestCase):
    def compile_helper(self, source_name: str, output: Path) -> None:
        result = subprocess.run(
            [
                "xcrun",
                "swiftc",
                str(HELPERS / source_name),
                "-o",
                str(output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unicode_helper_compiles_and_dry_run_decodes_codepoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "adv360-type-unicode"
            self.compile_helper("adv360-type-unicode.swift", binary)

            result = subprocess.run(
                [str(binary), "--dry-run", "0060"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "`\n")

    def test_input_source_helper_compiles_and_lists_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "adv360-input-source"
            self.compile_helper("adv360-input-source.swift", binary)

            result = subprocess.run(
                [str(binary), "list"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("com.apple.keylayout.ABC", result.stdout)

            normal = subprocess.run(
                [
                    str(binary),
                    "translate",
                    "com.apple.keylayout.ABC",
                    "0",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            shifted = subprocess.run(
                [
                    str(binary),
                    "translate",
                    "com.apple.keylayout.ABC",
                    "0",
                    "shift",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(normal.returncode, 0, normal.stderr)
            self.assertEqual(shifted.returncode, 0, shifted.stderr)
            self.assertEqual(normal.stdout, "a\n")
            self.assertEqual(shifted.stdout, "A\n")


if __name__ == "__main__":
    unittest.main()

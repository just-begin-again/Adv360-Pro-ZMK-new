import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "generate_symbols.py"
MANIFEST = ROOT / "host" / "symbols" / "manifest.json"


class SymbolGeneratorTests(unittest.TestCase):
    def run_generator(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GENERATOR), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_manifest_contract(self) -> None:
        result = self.run_generator("--validate", "--manifest", str(MANIFEST))

        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(MANIFEST.read_text())
        self.assertEqual(len(data["symbols"]), 33)

        tokens = [
            (item["token"]["key_code"], tuple(item["token"].get("modifiers", [])))
            for item in data["symbols"]
        ]
        self.assertEqual(len(tokens), len(set(tokens)))
        self.assertFalse(
            {"f19", "f20", "f21", "f22", "f23"}
            & {item["token"]["key_code"] for item in data["symbols"]}
        )

        # Carbon has no virtual key codes for F22-F24. These combinations
        # remain directly distinguishable by both Karabiner and .keylayout.
        fallback_compatible_tokens = {
            item["name"]: item["token"]["zmk"]
            for item in data["symbols"]
            if item["name"] in {"slash", "hash", "underscore"}
        }
        self.assertEqual(
            fallback_compatible_tokens,
            {
                "slash": "LS(F13)",
                "hash": "LS(F14)",
                "underscore": "LS(F15)",
            },
        )

        for item in data["symbols"]:
            self.assertIn("abc", item["outputs"])
            self.assertIn("russian_win", item["outputs"])

        unicode_text = {
            item["name"]
            for item in data["symbols"]
            if item["outputs"]["russian_win"]["type"] == "unicode_text"
        }
        self.assertEqual(unicode_text, {"grave", "tilde"})

    def test_generation_is_deterministic_and_check_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            generated = self.run_generator(
                "--manifest",
                str(MANIFEST),
                "--output-root",
                str(output),
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)

            checked = self.run_generator(
                "--check",
                "--manifest",
                str(MANIFEST),
                "--output-root",
                str(output),
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)

            dtsi = output / "config" / "generated" / "symbol_tokens.dtsi"
            dtsi.write_text(dtsi.read_text() + "\n// drift\n")

            drifted = self.run_generator(
                "--check",
                "--manifest",
                str(MANIFEST),
                "--output-root",
                str(output),
            )
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("generated file differs", drifted.stderr)

    def test_manifest_validation_rejects_missing_symbol(self) -> None:
        data = json.loads(MANIFEST.read_text())
        data["symbols"] = [
            item for item in data["symbols"] if item["name"] != "underscore"
        ]

        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps(data))
            result = self.run_generator(
                "--validate",
                "--manifest",
                str(manifest),
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing symbols: underscore", result.stderr)

    def test_generated_artifact_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = self.run_generator(
                "--manifest",
                str(MANIFEST),
                "--output-root",
                str(output),
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            dtsi = (
                output / "config" / "generated" / "symbol_tokens.dtsi"
            ).read_text()
            self.assertIn("#define SYM_EM_DASH", dtsi)
            self.assertIn("#define SYM_COMMA", dtsi)

            karabiner = json.loads(
                (
                    output
                    / "host"
                    / "karabiner"
                    / "adv360-symbols.json"
                ).read_text()
            )
            self.assertEqual(karabiner["title"], "Adv360 Managed Symbols")
            gate_rule, *decoders = karabiner["rules"]
            self.assertEqual(len(decoders), 2)
            devices = {
                (item["vendor_id"], item["product_id"])
                for item in json.loads(MANIFEST.read_text())["devices"]
            }
            gates = gate_rule["manipulators"]
            expected_variables = {"f22": "adv360_sym_left", "f23": "adv360_sym_right"}
            self.assertEqual({gate["from"]["key_code"] for gate in gates}, set(expected_variables))
            for gate in gates:
                hid_key = gate["from"]["key_code"]
                self.assertEqual(gate["from"]["modifiers"], {"optional": ["any"]})
                self.assertEqual(gate["to"], [{"set_variable": {
                    "name": expected_variables[hid_key], "value": 1, "key_up_value": 0,
                }}])
                self.assertEqual(len(gate["conditions"]), 1)
                device = gate["conditions"][0]
                self.assertEqual(device["type"], "device_if")
                self.assertEqual({
                    (item["vendor_id"], item["product_id"]) for item in device["identifiers"]
                }, devices)

            for decoder in decoders:
                self.assertEqual(len(decoder["manipulators"]), 33)
                for manipulator in decoder["manipulators"]:
                    self.assertEqual(
                        {condition["type"] for condition in manipulator["conditions"]},
                        {"device_if", "input_source_if", "expression_if"},
                    )
                    self.assertIn({
                        "type": "expression_if",
                        "expression": "adv360_sym_left + adv360_sym_right > 0",
                    }, manipulator["conditions"])

            language = json.loads(
                (
                    output
                    / "host"
                    / "karabiner"
                    / "adv360-language.json"
                ).read_text()
            )
            self.assertEqual(
                language["title"], "Adv360 Managed Input Sources"
            )
            from_keys = {
                manipulator["from"]["key_code"]
                for rule in language["rules"]
                for manipulator in rule["manipulators"]
            }
            self.assertEqual(from_keys, {"f19", "f20", "f21"})

            bundle = (
                output
                / "host"
                / "input-sources"
                / "Adv360Layouts.bundle"
                / "Contents"
            )
            self.assertTrue((bundle / "Info.plist").exists())
            self.assertTrue(
                (bundle / "Resources" / "Adv360 ABC.keylayout").exists()
            )
            self.assertTrue(
                (bundle / "Resources" / "Adv360 Russian-PC.keylayout").exists()
            )

    def test_keylayouts_use_numeric_references_for_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = self.run_generator(
                "--manifest",
                str(MANIFEST),
                "--output-root",
                str(output),
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            resources = (
                output
                / "host"
                / "input-sources"
                / "Adv360Layouts.bundle"
                / "Contents"
                / "Resources"
            )
            for keylayout in resources.glob("*.keylayout"):
                content = keylayout.read_text()
                illegal = [
                    character
                    for character in content
                    if ord(character) < 32
                    and character not in ("\n", "\r", "\t")
                ]
                self.assertEqual(illegal, [], keylayout.name)
                self.assertIn("&#x0010;", content)

    def test_artifact_validation_accepts_xml11_and_rejects_bad_structure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            generated = self.run_generator(
                "--manifest",
                str(MANIFEST),
                "--output-root",
                str(output),
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)

            valid = self.run_generator(
                "--validate-artifacts",
                "--manifest",
                str(MANIFEST),
                "--output-root",
                str(output),
            )
            self.assertEqual(valid.returncode, 0, valid.stderr)

            keylayout = (
                output
                / "host"
                / "input-sources"
                / "Adv360Layouts.bundle"
                / "Contents"
                / "Resources"
                / "Adv360 ABC.keylayout"
            )
            keylayout.write_text(
                keylayout.read_text().replace("</keyboard>", "</broken>")
            )

            invalid = self.run_generator(
                "--validate-artifacts",
                "--manifest",
                str(MANIFEST),
                "--output-root",
                str(output),
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("invalid keylayout XML structure", invalid.stderr)


if __name__ == "__main__":
    unittest.main()

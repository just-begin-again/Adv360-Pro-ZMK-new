import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from host.adv360_host import (
    HostPaths,
    MANAGED_PREFIX,
    device_gate,
    generate_aerospace_fragment,
    install,
    merge_karabiner_config,
    parse_hidutil_devices,
    restore,
    set_mode,
    verify,
    verify_fallback_symbol_tokens,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (ROOT / "host" / "symbols" / "manifest.json").read_text()
)


class HostIntegrationTests(unittest.TestCase):
    def test_aerospace_remaps_qwerty_physical_keys_to_colemak_keys(self) -> None:
        config = """
[mode.main.binding]
ctrl-shift-alt-n = 'focus left'
ctrl-shift-alt-e = 'focus down'
ctrl-shift-alt-u = 'focus up'
ctrl-shift-alt-i = 'focus right'
ctrl-shift-alt-cmd-n = 'move left'

[mode.service.binding]
ctrl-alt-shift-i = ['join-with right', 'mode main']
"""
        fragment = generate_aerospace_fragment(config, MANIFEST)
        self.assertEqual(fragment["title"], "Adv360 Managed AeroSpace")
        self.assertEqual(len(fragment["rules"]), 1)

        gate, *manipulators = fragment["rules"][0]["manipulators"]
        self.assertEqual(gate["type"], "basic")
        self.assertEqual(gate["from"], {
            "key_code": "f24",
            "modifiers": {"optional": ["any"]},
        })
        self.assertEqual(gate["to"], [{"set_variable": {
            "name": "adv360_meh_qwerty", "value": 1, "key_up_value": 0,
        }}])
        self.assertEqual(len(gate["conditions"]), 1)
        keyboard_condition = gate["conditions"][0]
        self.assertEqual(keyboard_condition["type"], "device_if")
        self.assertEqual(
            {(item["vendor_id"], item["product_id"], item["is_keyboard"])
             for item in keyboard_condition["identifiers"]},
            {(item["vendor_id"], item["product_id"], True)
             for item in MANIFEST["devices"]},
        )
        remaps = {
            (
                item["from"]["key_code"],
                tuple(item["from"]["modifiers"]["mandatory"]),
            ): item["to"][0]
            for item in manipulators
        }
        self.assertEqual(
            remaps[
                ("j", ("control", "option", "shift"))
            ],
            {
                "key_code": "n",
                "modifiers": [
                    "left_control",
                    "left_option",
                    "left_shift",
                ],
            },
        )
        self.assertEqual(
            remaps[
                ("j", ("command", "control", "option", "shift"))
            ]["key_code"],
            "n",
        )
        self.assertEqual(
            remaps[
                ("l", ("control", "option", "shift"))
            ]["key_code"],
            "i",
        )
        for item in manipulators:
            self.assertEqual(len(item["conditions"]), 2)
            self.assertEqual(item["conditions"][0], keyboard_condition)
            self.assertEqual(item["conditions"][1], {
                "type": "variable_if", "name": "adv360_meh_qwerty", "value": 1,
            })
            self.assertTrue(
                item["description"].startswith(MANAGED_PREFIX)
            )

    def test_merge_replaces_only_managed_complex_rules(self) -> None:
        original = {
            "profiles": [
                {
                    "name": "Default",
                    "selected": True,
                    "simple_modifications": [
                        {"from": {"key_code": "a"}, "to": [{"key_code": "b"}]}
                    ],
                    "devices": [
                        {
                            "identifiers": {"vendor_id": 1, "product_id": 2},
                            "simple_modifications": [
                                {
                                    "from": {"key_code": "c"},
                                    "to": [{"key_code": "d"}],
                                }
                            ],
                        }
                    ],
                    "complex_modifications": {
                        "rules": [
                            {
                                "description": "Keep me",
                                "manipulators": [],
                            },
                            {
                                "description": f"{MANAGED_PREFIX} Old",
                                "manipulators": [],
                            },
                        ]
                    },
                }
            ]
        }
        before_simple = copy.deepcopy(
            original["profiles"][0]["simple_modifications"]
        )
        before_devices = copy.deepcopy(original["profiles"][0]["devices"])
        fragments = [
            {
                "rules": [
                    {
                        "description": f"{MANAGED_PREFIX} New",
                        "manipulators": [],
                    }
                ]
            }
        ]

        merged = merge_karabiner_config(original, fragments)
        merged_again = merge_karabiner_config(merged, fragments)

        profile = merged["profiles"][0]
        self.assertEqual(profile["simple_modifications"], before_simple)
        self.assertEqual(profile["devices"], before_devices)
        self.assertEqual(
            [rule["description"] for rule in profile["complex_modifications"]["rules"]],
            ["Keep me", f"{MANAGED_PREFIX} New"],
        )
        self.assertEqual(merged_again, merged)

    def test_device_scoped_recovery_precedes_existing_global_f20_f21(self) -> None:
        legacy = [
            {
                "description": f"Old global {key}",
                "manipulators": [{"type": "basic", "from": {"key_code": key}}],
            }
            for key in ("f20", "f21")
        ]
        original = {"profiles": [{"complex_modifications": {"rules": legacy}}]}
        fragment = json.loads((ROOT / "host/karabiner/adv360-language.json").read_text())

        merged = merge_karabiner_config(original, [fragment])
        rules = merged["profiles"][0]["complex_modifications"]["rules"]
        for key in ("f20", "f21"):
            matching = [
                (rule, item)
                for rule in rules
                for item in rule["manipulators"]
                if item.get("from", {}).get("key_code") == key
            ]
            self.assertTrue(matching[0][0]["description"].startswith(MANAGED_PREFIX))
            self.assertEqual(matching[0][1]["conditions"][0]["type"], "device_if")
        self.assertEqual(
            [rule for rule in rules if not rule["description"].startswith(MANAGED_PREFIX)],
            legacy,
        )
        self.assertEqual(merge_karabiner_config(merged, [fragment]), merged)

    def test_device_gate_distinguishes_verified_bluetooth_and_usb(self) -> None:
        output = """
0x1d50 0x615e 0x401b4aef 1 6 0x100 Bluetooth Low Energy Driver Adv360 Pro
0x29ea 0x0362 0x1234 1 6 0x101 USB Driver Advantage360 Pro
"""
        connected = parse_hidutil_devices(output)
        status = device_gate(MANIFEST["devices"], connected)
        self.assertEqual(status["Adv360 Pro Bluetooth"], True)
        self.assertEqual(status["Adv360 Pro USB"], True)

        bluetooth_only = parse_hidutil_devices(output.splitlines()[1])
        status = device_gate(MANIFEST["devices"], bluetooth_only)
        self.assertEqual(status["Adv360 Pro Bluetooth"], True)
        self.assertEqual(status["Adv360 Pro USB"], False)

    def test_install_is_idempotent_and_restore_recovers_exact_inputs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            paths = HostPaths.for_home(home, ROOT)
            paths.karabiner_config.parent.mkdir(parents=True)
            original_karabiner = {
                "profiles": [{
                    "name": "Default",
                    "selected": True,
                    "simple_modifications": [{
                        "from": {"key_code": "a"},
                        "to": [{"key_code": "b"}],
                    }],
                    "devices": [{
                        "identifiers": {"vendor_id": 1, "product_id": 2},
                        "simple_modifications": [{
                            "from": {"key_code": "c"},
                            "to": [{"key_code": "d"}],
                        }],
                    }],
                    "complex_modifications": {
                        "rules": [{
                            "description": "Keep me",
                            "manipulators": [],
                        }]
                    },
                }]
            }
            paths.karabiner_config.write_text(
                json.dumps(original_karabiner, indent=2) + "\n"
            )
            original_aerospace = (
                "[mode.main.binding]\n"
                "ctrl-shift-alt-n = 'focus left'\n"
                "\n[mode.service.binding]\n"
                "ctrl-alt-shift-l = ['join-with right', 'mode main']\n"
            )
            paths.aerospace_config.write_text(original_aerospace)

            connected = {
                (item["vendor_id"], item["product_id"])
                for item in MANIFEST["devices"]
            }
            first_backup = install(
                paths,
                connected,
                compile_helpers=False,
            )
            installed = json.loads(paths.karabiner_config.read_text())
            profile = installed["profiles"][0]
            self.assertEqual(
                profile["simple_modifications"],
                original_karabiner["profiles"][0]["simple_modifications"],
            )
            self.assertEqual(
                profile["devices"],
                original_karabiner["profiles"][0]["devices"],
            )
            descriptions = [
                rule["description"]
                for rule in profile["complex_modifications"]["rules"]
            ]
            self.assertEqual(descriptions.count("Keep me"), 1)
            self.assertGreater(
                len([
                    item
                    for item in descriptions
                    if item.startswith(MANAGED_PREFIX)
                ]),
                2,
            )
            self.assertEqual(paths.aerospace_config.read_text(), original_aerospace)
            backup_entries = json.loads((first_backup / "manifest.json").read_text())["entries"]
            self.assertNotIn("aerospace", backup_entries)
            self.assertTrue(paths.installed_bundle.is_dir())
            self.assertEqual(paths.mode_file.read_text().strip(), "primary")

            second_backup = install(
                paths,
                connected,
                compile_helpers=False,
            )
            self.assertNotEqual(first_backup, second_backup)
            reinstalled = json.loads(paths.karabiner_config.read_text())
            descriptions = [
                rule["description"]
                for rule in reinstalled["profiles"][0][
                    "complex_modifications"
                ]["rules"]
            ]
            self.assertEqual(len(descriptions), len(set(descriptions)))

            later_aerospace = original_aerospace + "\n# User edit after install\n"
            paths.aerospace_config.write_text(later_aerospace)
            restore(paths, first_backup)
            self.assertEqual(
                json.loads(paths.karabiner_config.read_text()),
                original_karabiner,
            )
            self.assertEqual(
                paths.aerospace_config.read_text(), later_aerospace
            )
            self.assertFalse(paths.installed_bundle.exists())

    def test_install_does_not_require_aerospace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = HostPaths.for_home(Path(directory), ROOT)
            paths.karabiner_config.parent.mkdir(parents=True)
            paths.karabiner_config.write_text('{"profiles":[{"selected":true}]}')
            connected = {
                (item["vendor_id"], item["product_id"])
                for item in MANIFEST["devices"]
            }

            install(paths, connected, compile_helpers=False)

            self.assertFalse(paths.aerospace_config.exists())
            rules = json.loads(paths.karabiner_config.read_text())["profiles"][0][
                "complex_modifications"
            ]["rules"]
            aero = next(rule for rule in rules if "physical QWERTY" in rule["description"])
            self.assertEqual([item["from"]["key_code"] for item in aero["manipulators"]], ["f24"])

    def test_install_refuses_unverified_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            paths = HostPaths.for_home(home, ROOT)
            paths.karabiner_config.parent.mkdir(parents=True)
            paths.karabiner_config.write_text(
                '{"profiles":[{"selected":true,'
                '"complex_modifications":{"rules":[]}}]}'
            )
            paths.aerospace_config.write_text("[mode.main.binding]\n")

            with self.assertRaisesRegex(
                RuntimeError, "Adv360 Pro USB"
            ):
                install(
                    paths,
                    {(7504, 24926)},
                    compile_helpers=False,
                    )

    def test_mode_selects_pair_and_verify_reports_install_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            paths = HostPaths.for_home(home, ROOT)
            paths.state_dir.mkdir(parents=True)
            paths.installed_bundle.mkdir(parents=True)
            selected = []

            set_mode(paths, "fallback", selected.append)
            set_mode(paths, "primary", selected.append)

            self.assertEqual(
                selected,
                [
                    "com.rsushkevich.keylayout.Adv360ABC",
                    "com.apple.keylayout.ABC",
                ],
            )
            self.assertEqual(paths.mode_file.read_text().strip(), "primary")
            problems = verify(
                paths,
                {
                    (item["vendor_id"], item["product_id"])
                    for item in MANIFEST["devices"]
                },
                require_installed=False,
            )
            self.assertEqual(problems, [])

    def test_aerospace_generator_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "aerospace.json"
            command = [
                sys.executable,
                str(ROOT / "tools" / "generate_aerospace_rules.py"),
                "--config",
                str(ROOT / "tests" / "fixtures" / "aerospace.toml"),
                "--output",
                str(output),
            ]
            generated = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)

            checked = subprocess.run(
                command + ["--check"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)

            output.write_text(output.read_text() + "\n")
            drifted = subprocess.run(
                command + ["--check"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("generated file differs", drifted.stderr)

    def test_fallback_symbol_verifier_checks_both_sources(self) -> None:
        calls = []

        def translator(source: str, key_code: int, shifted: bool) -> str:
            calls.append((source, key_code, shifted))
            for symbol in MANIFEST["symbols"]:
                token = symbol["token"]
                if (
                    token["mac_key_code"] == key_code
                    and ("left_shift" in token.get("modifiers", [])) == shifted
                ):
                    return symbol["unicode"]
            raise AssertionError("unexpected token")

        self.assertEqual(
            verify_fallback_symbol_tokens(MANIFEST, translator),
            [],
        )
        self.assertEqual(len(calls), 66)

        def broken(source: str, key_code: int, shifted: bool) -> str:
            value = translator(source, key_code, shifted)
            return "!" if key_code == 105 and not shifted else value

        problems = verify_fallback_symbol_tokens(MANIFEST, broken)
        self.assertTrue(any("tilde" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEYMAP_PATH = ROOT / "config" / "adv360.keymap"
LEFT_DEFCONFIG = (
    ROOT / "config" / "boards" / "arm" / "adv360" / "adv360_left_defconfig"
)


def keymap_text() -> str:
    return KEYMAP_PATH.read_text()


def layer_names(content: str) -> list[str]:
    keymap = content.split("keymap {", 1)[1]
    return re.findall(r"^\s{8}([a-zA-Z0-9_]+)\s*\{", keymap, re.MULTILINE)


def layer_bindings(content: str, name: str) -> list[str]:
    match = re.search(
        rf"^\s{{8}}{re.escape(name)}\s*\{{.*?bindings\s*=\s*<(.*?)>;",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"layer not found: {name}")
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", match.group(1), flags=re.DOTALL)
    return [
        " ".join(binding.split())
        for binding in re.findall(r"&([^&]+?)(?=\s+&|$)", body, re.DOTALL)
    ]


class KeymapContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.content = keymap_text()

    def test_layer_contract_and_binding_counts(self) -> None:
        expected = [
            "default_layer",
            "layer_colemak_dh",
            "layer_keypad",
            "layer_fn",
            "layer_mod",
            "layer_symbols",
            "layer_left_arrows",
            "layer_right_arrows",
            "layer_nav",
            "layer_precision",
            "layer_warp",
            "layer_scroll",
        ]
        self.assertEqual(layer_names(self.content), expected)
        for name in expected:
            self.assertEqual(len(layer_bindings(self.content, name)), 76, name)

    def test_extended_hid_preserves_the_meh_marker(self) -> None:
        self.assertIn(
            "CONFIG_ZMK_HID_KEYBOARD_EXTENDED_REPORT=y",
            LEFT_DEFCONFIG.read_text(),
        )

    def test_adv360_keymap_is_the_only_editor_source(self) -> None:
        self.assertFalse((ROOT / "config" / "keymap.json").exists())
        documentation = (ROOT / "docs" / "unified-layout.md").read_text()
        self.assertIn("Edit only `config/adv360.keymap`.", documentation)
        self.assertIn(
            "`config/keymap.json` is obsolete and intentionally removed.",
            documentation,
        )

    def test_symbol_positions_preserve_legacy_taps_and_holds(self) -> None:
        for base in ("default_layer", "layer_colemak_dh"):
            bindings = layer_bindings(self.content, base)
            self.assertEqual(bindings[35], "mo 5")
            self.assertEqual(bindings[38], "mo 5")

        symbols = layer_bindings(self.content, "layer_symbols")
        # Nontransparent positions from the firmware captured before the update.
        original = {
            6: "tog 2",
            15: "kp ESCAPE",
            20: "to 0",
            23: "mt ASTRK SLASH",
            24: "kp PLUS",
            25: "mt PIPE AMPERSAND",
            26: "kp HASH",
            28: "kp ESC",
            29: "kp LEFT_BRACE",
            30: "kp LT",
            31: "kp GREATER_THAN",
            32: "kp RIGHT_BRACE",
            34: "to 1",
            40: "kp GRAVE",
            41: "mt SINGLE_QUOTE DOUBLE_QUOTES",
            42: "mt COMMA DOT",
            43: "kp EQUAL",
            44: "mt SEMICOLON COLON",
            47: "kp LEFT_PARENTHESIS",
            48: "kp LEFT_BRACKET",
            49: "kp RIGHT_BRACKET",
            50: "kp RIGHT_PARENTHESIS",
            55: "mt QUESTION EXCL",
            56: "mt UNDERSCORE MINUS",
            57: "kp AT",
            70: "kp ESCAPE",
        }
        self.assertEqual(symbols, [original.get(i, "trans") for i in range(76)])

    def test_original_home_row_mods_tap_dances_and_caps_toggle(self) -> None:
        behavior = self.content.split("hm: homerow_mods {", 1)[1].split("};", 1)[0]
        self.assertIn("tapping-term-ms = <300>;", behavior)
        self.assertIn("quick_tap_ms = <250>;", behavior)
        self.assertIn('flavor = "tap-preferred";', behavior)
        qwerty = layer_bindings(self.content, "default_layer")
        colemak = layer_bindings(self.content, "layer_colemak_dh")
        for index, first, second in (
            (30, "hm LCTRL S", "hm LCTRL R"), (31, "hm LEFT_ALT D", "hm LEFT_ALT S"),
            (32, "hm LEFT_GUI F", "hm LEFT_GUI T"), (41, "hm RIGHT_GUI J", "hm RIGHT_GUI N"),
            (42, "hm RIGHT_ALT K", "hm RIGHT_ALT E"), (43, "hm RCTRL L", "hm RCTRL I"),
            (49, "copy_and_clipboard", "copy_and_clipboard"), (50, "paste_w_V", "paste_w_D"),
            (52, "screenshots_and_ocr", "screenshots_and_ocr"),
            (53, "kp CAPS", "kp CAPS"),
            (60, "switch_to_colemak_dh", "switch_to_qwerty"),
        ):
            self.assertEqual((qwerty[index], colemak[index]), (first, second), index)
        self.assertIn("bindings = <&kp CAPSLOCK>, <&macro_press>, <&to 1>;", self.content)
        self.assertIn("bindings = <&kp CAPSLOCK>, <&macro_wait_time 75>, <&to 0>;", self.content)

    def test_qwerty_thumb_marker_is_absent_in_colemak(self) -> None:
        for position, tap in ((66, "DELETE"), (70, "SPACE")):
            self.assertEqual(layer_bindings(self.content, "default_layer")[position],
                             f"meh_qwerty_tap 0 {tap}")
            self.assertEqual(layer_bindings(self.content, "layer_colemak_dh")[position],
                             f"mt ADV360_MEH {tap}")
        self.assertIn("#define ADV360_MEH RC(LA(LSHFT))", self.content)
        self.assertIn("<&macro_press &kp F24 &kp ADV360_MEH>", self.content)
        self.assertIn("<&macro_release &kp ADV360_MEH &kp F24>", self.content)

    def test_nav_mouse_contract(self) -> None:
        for base in ("default_layer", "layer_colemak_dh"):
            bindings = layer_bindings(self.content, base)
            self.assertEqual((bindings[67], bindings[68], bindings[75]),
                             ("mo 7", "mo 6", "tog 8"))

        nav = layer_bindings(self.content, "layer_nav")
        expected = {
            15: "kp LG(LBKT)",
            16: "kp LG(LS(LEFT_BRACKET))",
            17: "kp LG(LS(RIGHT_BRACKET))",
            18: "kp LG(RIGHT_BRACKET)",
            19: "mo 10",
            23: "msc SCRL_LEFT",
            24: "mmv MOVE_UP",
            25: "msc SCRL_RIGHT",
            33: "mo 9",
            41: "mmv MOVE_LEFT",
            42: "mmv MOVE_DOWN",
            43: "mmv MOVE_RIGHT",
            51: "mo 11",
            55: "msc SCRL_UP",
            57: "msc SCRL_DOWN",
            69: "mkp RCLK",
            70: "mkp LCLK",
            75: "trans",
        }
        for position, binding in expected.items():
            self.assertEqual(nav[position], binding, position)

    def test_mouse_speed_and_scroll_layers(self) -> None:
        self.assertIn("#define ZMK_POINTING_DEFAULT_MOVE_VAL 1400", self.content)
        self.assertIn("#define ZMK_POINTING_DEFAULT_SCRL_VAL 20", self.content)
        self.assertIn("time-to-max-speed-ms = <500>;", self.content)
        self.assertIn("acceleration-exponent = <1>;", self.content)
        self.assertIn("layers = <9>;", self.content)
        self.assertIn("input-processors = <&zip_xy_scaler 1 3>;", self.content)
        self.assertIn("layers = <10>;", self.content)
        self.assertIn("input-processors = <&zip_xy_scaler 5 2>;", self.content)

        scroll = layer_bindings(self.content, "layer_scroll")
        self.assertEqual(scroll[24], "msc SCRL_UP")
        self.assertEqual(scroll[41], "msc SCRL_LEFT")
        self.assertEqual(scroll[42], "msc SCRL_DOWN")
        self.assertEqual(scroll[43], "msc SCRL_RIGHT")

        first_include = self.content.index("#include")
        self.assertLess(
            self.content.index("#define ZMK_POINTING_DEFAULT_MOVE_VAL 1400"),
            first_include,
        )
        self.assertLess(
            self.content.index("#define ZMK_POINTING_DEFAULT_SCRL_VAL 20"),
            first_include,
        )


if __name__ == "__main__":
    unittest.main()

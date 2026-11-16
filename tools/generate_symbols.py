#!/usr/bin/env python3

import argparse
import json
import plistlib
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "host" / "symbols" / "manifest.json"

REQUIRED_SYMBOLS = frozenset({
    "tilde",
    "dollar",
    "percent",
    "caret",
    "backslash",
    "left_brace",
    "less_than",
    "greater_than",
    "right_brace",
    "left_parenthesis",
    "left_bracket",
    "right_bracket",
    "right_parenthesis",
    "pipe",
    "equal",
    "asterisk",
    "plus",
    "at",
    "ampersand",
    "grave",
    "colon",
    "semicolon",
    "comma",
    "period",
    "em_dash",
    "minus",
    "question",
    "exclamation",
    "double_quote",
    "single_quote",
    "slash",
    "hash",
    "underscore",
})

BASE_MAPS = {
    "abc": {
        "normal": {
            0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z",
            7: "x", 8: "c", 9: "v", 10: "§", 11: "b", 12: "q", 13: "w",
            14: "e", 15: "r", 16: "y", 17: "t", 18: "1", 19: "2",
            20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9",
            26: "7", 27: "-", 28: "8", 29: "0", 30: "]", 31: "o",
            32: "u", 33: "[", 34: "i", 35: "p", 36: "\r", 37: "l",
            38: "j", 39: "'", 40: "k", 41: ";", 42: "\\", 43: ",",
            44: "/", 45: "n", 46: "m", 47: ".", 48: "\t", 49: " ",
            50: "`", 51: "\b", 52: "\u0003", 53: "\u001b",
        },
        "shift": {
            0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z",
            7: "X", 8: "C", 9: "V", 10: "±", 11: "B", 12: "Q", 13: "W",
            14: "E", 15: "R", 16: "Y", 17: "T", 18: "!", 19: "@",
            20: "#", 21: "$", 22: "^", 23: "%", 24: "+", 25: "(",
            26: "&", 27: "_", 28: "*", 29: ")", 30: "}", 31: "O",
            32: "U", 33: "{", 34: "I", 35: "P", 36: "\r", 37: "L",
            38: "J", 39: "\"", 40: "K", 41: ":", 42: "|", 43: "<",
            44: "?", 45: "N", 46: "M", 47: ">", 48: "\t", 49: " ",
            50: "~", 51: "\b", 52: "\u0003", 53: "\u001b",
        },
    },
    "russian_win": {
        "normal": {
            0: "ф", 1: "ы", 2: "в", 3: "а", 4: "р", 5: "п", 6: "я",
            7: "ч", 8: "с", 9: "м", 10: "ё", 11: "и", 12: "й", 13: "ц",
            14: "у", 15: "к", 16: "н", 17: "е", 18: "1", 19: "2",
            20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9",
            26: "7", 27: "-", 28: "8", 29: "0", 30: "ъ", 31: "щ",
            32: "г", 33: "х", 34: "ш", 35: "з", 36: "\r", 37: "д",
            38: "о", 39: "э", 40: "л", 41: "ж", 42: "\\", 43: "б",
            44: ".", 45: "т", 46: "ь", 47: "ю", 48: "\t", 49: " ",
            50: "ё", 51: "\b", 52: "\u0003", 53: "\u001b",
        },
        "shift": {
            0: "Ф", 1: "Ы", 2: "В", 3: "А", 4: "Р", 5: "П", 6: "Я",
            7: "Ч", 8: "С", 9: "М", 10: "Ё", 11: "И", 12: "Й", 13: "Ц",
            14: "У", 15: "К", 16: "Н", 17: "Е", 18: "!", 19: "\"",
            20: "№", 21: ";", 22: ":", 23: "%", 24: "+", 25: "(",
            26: "?", 27: "_", 28: "*", 29: ")", 30: "Ъ", 31: "Щ",
            32: "Г", 33: "Х", 34: "Ш", 35: "З", 36: "\r", 37: "Д",
            38: "О", 39: "Э", 40: "Л", 41: "Ж", 42: "/", 43: "Б",
            44: ",", 45: "Т", 46: "Ь", 47: "Ю", 48: "\t", 49: " ",
            50: "Ё", 51: "\b", 52: "\u0003", 53: "\u001b",
        },
    },
}

SPECIAL_KEYS = {
    65: ".", 66: "\u001d", 67: "*", 69: "+", 70: "\u001c",
    71: "\u001b", 72: "\u001f", 75: "/", 76: "\u0003", 77: "\u001e",
    78: "-", 81: "=", 82: "0", 83: "1", 84: "2", 85: "3",
    86: "4", 87: "5", 88: "6", 89: "7", 91: "8", 92: "9",
    96: "\u0010", 97: "\u0010", 98: "\u0010", 99: "\u0010",
    100: "\u0010", 101: "\u0010", 102: "\u0010", 103: "\u0010",
    104: "\u0010", 105: "\u0010", 106: "\u0010", 107: "\u0010",
    108: "\u0010", 109: "\u0010", 110: "\u0010", 111: "\u0010",
    112: "\u0010", 113: "\u0010", 114: "\u0005", 115: "\u0001",
    116: "\u000b", 117: "\u007f", 118: "\u0010", 119: "\u0004",
    120: "\u0010", 121: "\u000c", 122: "\u0010", 123: "\u001c",
    124: "\u001d", 125: "\u001f", 126: "\u001e",
}

INPUT_SOURCE_IDS = {
    "abc": "^com\\.apple\\.keylayout\\.ABC$",
    "russian_win": "^com\\.apple\\.keylayout\\.RussianWin$",
}

SYMBOL_LAYER_KEYS = {
    "f22": "adv360_sym_left",
    "f23": "adv360_sym_right",
}

INPUT_SOURCE_PAIRS = (
    {
        "label": "Primary",
        "en_condition": "^com\\.apple\\.keylayout\\.ABC$",
        "ru_condition": "^com\\.apple\\.keylayout\\.RussianWin$",
        "en_select": "com.apple.keylayout.ABC",
        "ru_select": "com.apple.keylayout.RussianWin",
    },
    {
        "label": "Fallback",
        "en_condition": (
            "^com\\.rsushkevich\\.keylayout\\.Adv360ABC$"
        ),
        "ru_condition": (
            "^com\\.rsushkevich\\.keylayout\\.Adv360RussianPC$"
        ),
        "en_select": "com.rsushkevich.keylayout.Adv360ABC",
        "ru_select": "com.rsushkevich.keylayout.Adv360RussianPC",
    },
)

CONTROL_REFERENCE = re.compile(r"&#x([0-9A-Fa-f]+);")


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


def validate_manifest(data: dict) -> None:
    if data.get("version") != 1:
        raise ValueError("manifest version must be 1")

    names = set()
    tokens = set()
    reserved = set(data.get("reserved_key_codes", [])).union(SYMBOL_LAYER_KEYS)
    for symbol in data.get("symbols", []):
        name = symbol["name"]
        if name in names:
            raise ValueError(f"duplicate symbol name: {name}")
        names.add(name)

        token = symbol["token"]
        key = token["key_code"]
        modifiers = tuple(token.get("modifiers", []))
        identity = (key, modifiers)
        if identity in tokens:
            raise ValueError(f"duplicate token: {identity}")
        tokens.add(identity)
        if key in reserved:
            raise ValueError(f"reserved token used: {key}")

        if "zmk" not in token or "mac_key_code" not in token:
            raise ValueError(f"incomplete token for {name}")

        for layout in ("abc", "russian_win"):
            output = symbol["outputs"].get(layout)
            if not output:
                raise ValueError(f"missing {layout} output for {name}")
            if output["type"] not in ("key", "unicode_text"):
                raise ValueError(f"unsupported output type for {name}")

    missing = sorted(REQUIRED_SYMBOLS - names)
    if missing:
        raise ValueError("missing symbols: " + ", ".join(missing))
    unexpected = sorted(names - REQUIRED_SYMBOLS)
    if unexpected:
        raise ValueError("unexpected symbols: " + ", ".join(unexpected))


def symbol_macro(name: str) -> str:
    return "SYM_" + name.upper()


def render_dtsi(data: dict) -> str:
    lines = [
        "/* Generated by tools/generate_symbols.py. Do not edit. */",
        "#pragma once",
        "",
    ]
    for symbol in data["symbols"]:
        lines.append(
            f"#define {symbol_macro(symbol['name'])} {symbol['token']['zmk']}"
        )
    return "\n".join(lines) + "\n"


def device_condition(data: dict) -> dict:
    return {
        "type": "device_if",
        "identifiers": [
            {
                "description": item["description"],
                "vendor_id": item["vendor_id"],
                "product_id": item["product_id"],
                "is_keyboard": True,
            }
            for item in data["devices"]
        ],
    }


def from_event(token: dict) -> dict:
    result = {"key_code": token["key_code"]}
    modifiers = token.get("modifiers", [])
    result["modifiers"] = {"optional": ["any"]}
    if modifiers:
        result["modifiers"]["mandatory"] = modifiers
    return result


def to_event(output: dict) -> list:
    if output["type"] == "unicode_text":
        codepoint = f"{ord(output['text']):04X}"
        return [{
            "shell_command": (
                "$HOME/.local/bin/adv360-type-unicode " + codepoint
            )
        }]

    event = {"key_code": output["key_code"]}
    if output.get("modifiers"):
        event["modifiers"] = output["modifiers"]
    return [event]


def render_karabiner(data: dict) -> str:
    device = device_condition(data)
    layer_active = {
        "type": "expression_if",
        "expression": " + ".join(SYMBOL_LAYER_KEYS.values()) + " > 0",
    }
    rules = [{
        "description": "[Adv360 Managed] Track held symbol thumbs",
        "manipulators": [
            {
                "type": "basic",
                "from": from_event({"key_code": key}),
                "to": [{"set_variable": {
                    "name": variable,
                    "value": 1,
                    "key_up_value": 0,
                }}],
                "conditions": [device],
            }
            for key, variable in SYMBOL_LAYER_KEYS.items()
        ],
    }]
    for layout, label in (("abc", "ABC"), ("russian_win", "RussianWin")):
        manipulators = []
        symbols = sorted(
            data["symbols"],
            key=lambda item: bool(item["token"].get("modifiers")),
            reverse=True,
        )
        for symbol in symbols:
            manipulators.append({
                "type": "basic",
                "from": from_event(symbol["token"]),
                "to": to_event(symbol["outputs"][layout]),
                "conditions": [
                    device,
                    layer_active,
                    {
                        "type": "input_source_if",
                        "input_sources": [{
                            "input_source_id": INPUT_SOURCE_IDS[layout]
                        }],
                    },
                ],
                "description": symbol["name"],
            })
        rules.append({
            "description": f"[Adv360 Managed] Decode symbols in {label}",
            "manipulators": manipulators,
        })

    return json.dumps(
        {"title": "Adv360 Managed Symbols", "rules": rules},
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def input_source_condition(*source_ids: str) -> dict:
    return {
        "type": "input_source_if",
        "input_sources": [
            {"input_source_id": source_id} for source_id in source_ids
        ],
    }


def select_input_source(source_id: str) -> list:
    return [{"select_input_source": {"input_source_id": source_id}}]


def render_language_karabiner(data: dict) -> str:
    toggle = []
    recover_en = []
    recover_ru = []
    for pair in INPUT_SOURCE_PAIRS:
        common = [device_condition(data)]
        toggle.extend([
            {
                "type": "basic",
                "from": {"key_code": "f19"},
                "to": select_input_source(pair["ru_select"]),
                "conditions": common + [
                    input_source_condition(pair["en_condition"])
                ],
                "description": f"{pair['label']}: EN to RU",
            },
            {
                "type": "basic",
                "from": {"key_code": "f19"},
                "to": select_input_source(pair["en_select"]),
                "conditions": common + [
                    input_source_condition(pair["ru_condition"])
                ],
                "description": f"{pair['label']}: RU to EN",
            },
        ])
        pair_condition = input_source_condition(
            pair["en_condition"], pair["ru_condition"]
        )
        recover_en.append({
            "type": "basic",
            "from": {"key_code": "f20"},
            "to": select_input_source(pair["en_select"]),
            "conditions": common + [pair_condition],
            "description": f"{pair['label']}: recover EN",
        })
        recover_ru.append({
            "type": "basic",
            "from": {"key_code": "f21"},
            "to": select_input_source(pair["ru_select"]),
            "conditions": common + [pair_condition],
            "description": f"{pair['label']}: recover RU",
        })

    rules = [
        {
            "description": "[Adv360 Managed] Toggle input source (F19)",
            "manipulators": toggle,
        },
        {
            "description": "[Adv360 Managed] Recover EN input source (F20)",
            "manipulators": recover_en,
        },
        {
            "description": "[Adv360 Managed] Recover RU input source (F21)",
            "manipulators": recover_ru,
        },
    ]
    return json.dumps(
        {"title": "Adv360 Managed Input Sources", "rules": rules},
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def full_base_map(layout: str, shifted: bool) -> dict[int, str]:
    key = "shift" if shifted else "normal"
    result = dict(SPECIAL_KEYS)
    result.update(BASE_MAPS[layout][key])
    return result


def token_overrides(data: dict, shifted: bool) -> dict[int, str]:
    result = {}
    for symbol in data["symbols"]:
        token_shifted = "left_shift" in symbol["token"].get("modifiers", [])
        if token_shifted == shifted:
            result[symbol["token"]["mac_key_code"]] = symbol["unicode"]
    return result


def add_key_map(parent: ET.Element, index: int, values: dict[int, str]) -> None:
    key_map = ET.SubElement(parent, "keyMap", {"index": str(index)})
    for code, output in sorted(values.items()):
        if len(output) == 1 and (ord(output) < 32 or ord(output) == 127):
            output = f"__CONTROL_{ord(output):04X}__"
        ET.SubElement(
            key_map,
            "key",
            {"code": str(code), "output": output},
        )


def render_keylayout(data: dict, layout: str, name: str, layout_id: int) -> str:
    keyboard = ET.Element(
        "keyboard",
        {
            "group": "126",
            "id": str(layout_id),
            "name": name,
            "maxout": "2",
        },
    )
    layouts = ET.SubElement(keyboard, "layouts")
    for first, last in (
        ("0", "17"), ("18", "18"), ("21", "23"), ("30", "30"),
        ("194", "194"), ("197", "197"), ("200", "201"),
    ):
        ET.SubElement(
            layouts,
            "layout",
            {"first": first, "last": last, "mapSet": "main", "modifiers": "mods"},
        )

    modifier_map = ET.SubElement(
        keyboard, "modifierMap", {"id": "mods", "defaultIndex": "0"}
    )
    normal = ET.SubElement(modifier_map, "keyMapSelect", {"mapIndex": "0"})
    ET.SubElement(normal, "modifier", {"keys": "command?"})
    ET.SubElement(normal, "modifier", {"keys": "anyOption? command?"})
    ET.SubElement(normal, "modifier", {"keys": "control"})
    shifted = ET.SubElement(modifier_map, "keyMapSelect", {"mapIndex": "1"})
    ET.SubElement(shifted, "modifier", {"keys": "anyShift caps? command?"})
    ET.SubElement(
        shifted, "modifier", {"keys": "anyShift caps? anyOption command?"}
    )
    ET.SubElement(shifted, "modifier", {"keys": "caps"})

    key_map_set = ET.SubElement(keyboard, "keyMapSet", {"id": "main"})
    base = full_base_map(layout, shifted=False)
    base.update(token_overrides(data, shifted=False))
    shift = full_base_map(layout, shifted=True)
    shift.update(token_overrides(data, shifted=False))
    shift.update(token_overrides(data, shifted=True))
    add_key_map(key_map_set, 0, base)
    add_key_map(key_map_set, 1, shift)

    ET.indent(keyboard, space="    ")
    body = ET.tostring(keyboard, encoding="unicode")
    for value in list(range(32)) + [127]:
        body = body.replace(
            f"__CONTROL_{value:04X}__", f"&#x{value:04X};"
        )
    return (
        '<?xml version="1.1" encoding="UTF-8"?>\n'
        '<!DOCTYPE keyboard SYSTEM '
        '"file://localhost/System/Library/DTDs/KeyboardLayout.dtd">\n'
        + body
        + "\n"
    )


def render_plist() -> bytes:
    return plistlib.dumps({
        "CFBundleIdentifier": "com.rsushkevich.keylayout.Adv360",
        "CFBundleName": "Adv360 Layouts",
        "CFBundleVersion": "1.0.0",
        "KLInfo_Adv360 ABC": {
            "TICapsLockLanguageSwitchCapable": False,
            "TISInputSourceID": "com.rsushkevich.keylayout.Adv360ABC",
            "TISIntendedLanguage": "en",
        },
        "KLInfo_Adv360 Russian-PC": {
            "TICapsLockLanguageSwitchCapable": False,
            "TISInputSourceID": "com.rsushkevich.keylayout.Adv360RussianPC",
            "TISIntendedLanguage": "ru",
        },
    })


def artifacts(data: dict) -> dict[Path, bytes]:
    bundle = Path(
        "host/input-sources/Adv360Layouts.bundle/Contents"
    )
    return {
        Path("config/generated/symbol_tokens.dtsi"):
            render_dtsi(data).encode(),
        Path("host/karabiner/adv360-symbols.json"):
            render_karabiner(data).encode(),
        Path("host/karabiner/adv360-language.json"):
            render_language_karabiner(data).encode(),
        bundle / "Info.plist": render_plist(),
        bundle / "Resources/Adv360 ABC.keylayout":
            render_keylayout(data, "abc", "Adv360 ABC", -32001).encode(),
        bundle / "Resources/Adv360 Russian-PC.keylayout":
            render_keylayout(
                data, "russian_win", "Adv360 Russian-PC", -32002
            ).encode(),
    }


def write_or_check(
    generated: dict[Path, bytes], output_root: Path, check: bool
) -> None:
    errors = []
    for relative, content in generated.items():
        target = output_root / relative
        if check:
            if not target.exists() or target.read_bytes() != content:
                errors.append(f"generated file differs: {relative}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    if errors:
        raise ValueError("\n".join(errors))


def validate_keylayout(path: Path) -> None:
    content = path.read_text()
    if not content.startswith('<?xml version="1.1" encoding="UTF-8"?>'):
        raise ValueError(f"keylayout must declare XML 1.1: {path}")

    illegal = [
        character
        for character in content
        if ord(character) < 32 and character not in ("\n", "\r", "\t")
    ]
    if illegal:
        raise ValueError(f"literal control character in keylayout: {path}")

    def replace_restricted_control(match: re.Match[str]) -> str:
        value = int(match.group(1), 16)
        if value == 0:
            raise ValueError(f"invalid XML control reference in {path}: U+0000")
        if 1 <= value < 32 or 0x7F <= value <= 0x9F:
            return f"CONTROL_{value:04X}"
        return match.group(0)

    sanitized = CONTROL_REFERENCE.sub(replace_restricted_control, content)
    try:
        root = ET.fromstring(sanitized)
    except ET.ParseError as error:
        raise ValueError(
            f"invalid keylayout XML structure: {path}: {error}"
        ) from error

    if root.tag != "keyboard":
        raise ValueError(f"invalid keylayout root element: {path}")
    if root.find("modifierMap") is None or root.find("keyMapSet") is None:
        raise ValueError(f"incomplete keylayout structure: {path}")


def validate_artifacts(output_root: Path) -> None:
    dtsi = output_root / "config/generated/symbol_tokens.dtsi"
    if not dtsi.is_file():
        raise ValueError(f"missing generated artifact: {dtsi}")

    karabiner = output_root / "host/karabiner/adv360-symbols.json"
    with karabiner.open() as handle:
        rules = json.load(handle)
    if not isinstance(rules.get("rules"), list):
        raise ValueError(f"invalid Karabiner rules artifact: {karabiner}")

    bundle = output_root / "host/input-sources/Adv360Layouts.bundle/Contents"
    with (bundle / "Info.plist").open("rb") as handle:
        plist = plistlib.load(handle)
    if plist.get("CFBundleIdentifier") != "com.rsushkevich.keylayout.Adv360":
        raise ValueError("invalid fallback input-source bundle identifier")

    resources = bundle / "Resources"
    keylayouts = sorted(resources.glob("*.keylayout"))
    if len(keylayouts) != 2:
        raise ValueError(f"expected two keylayouts in {resources}")
    for keylayout in keylayouts:
        validate_keylayout(keylayout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-root", type=Path, default=ROOT)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--validate-artifacts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = load_manifest(args.manifest)
        validate_manifest(data)
        if args.validate_artifacts:
            validate_artifacts(args.output_root)
        elif not args.validate:
            write_or_check(artifacts(data), args.output_root, args.check)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

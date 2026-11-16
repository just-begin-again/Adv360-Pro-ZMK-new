#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MANAGED_PREFIX = "[Adv360 Managed]"
EARLY_MANAGED_RULES = {
    f"{MANAGED_PREFIX} Toggle input source (F19)",
    f"{MANAGED_PREFIX} Recover EN input source (F20)",
    f"{MANAGED_PREFIX} Recover RU input source (F21)",
    f"{MANAGED_PREFIX} Track held symbol thumbs",
    f"{MANAGED_PREFIX} Decode symbols in ABC",
    f"{MANAGED_PREFIX} Decode symbols in RussianWin",
}

QWERTY_TO_COLEMAK = {
    "q": "q",
    "w": "w",
    "e": "f",
    "r": "p",
    "t": "b",
    "y": "j",
    "u": "l",
    "i": "u",
    "o": "y",
    "p": "semicolon",
    "a": "a",
    "s": "r",
    "d": "s",
    "f": "t",
    "g": "g",
    "h": "m",
    "j": "n",
    "k": "e",
    "l": "i",
    "semicolon": "o",
    "z": "z",
    "x": "x",
    "c": "c",
    "v": "d",
    "b": "v",
    "n": "k",
    "m": "h",
    "comma": "comma",
    "period": "period",
    "slash": "slash",
}

MEH_QWERTY_VARIABLE = "adv360_meh_qwerty"
ADV360_BLUETOOTH = (7504, 24926)

MODIFIER_NAMES = {"cmd", "ctrl", "alt", "shift"}
MEH = frozenset({"ctrl", "alt", "shift"})
HYPER = frozenset({"cmd", "ctrl", "alt", "shift"})

PRIMARY_EN = "com.apple.keylayout.ABC"
FALLBACK_EN = "com.rsushkevich.keylayout.Adv360ABC"
FALLBACK_RU = "com.rsushkevich.keylayout.Adv360RussianPC"


@dataclass(frozen=True)
class HostPaths:
    home: Path
    repo_root: Path
    karabiner_config: Path
    aerospace_config: Path
    installed_bundle: Path
    local_bin: Path
    support_dir: Path
    state_dir: Path
    mode_file: Path

    @classmethod
    def for_home(cls, home: Path, repo_root: Path) -> "HostPaths":
        state_dir = home / ".local" / "state" / "adv360-host"
        return cls(
            home=home,
            repo_root=repo_root,
            karabiner_config=(
                home / ".config" / "karabiner" / "karabiner.json"
            ),
            aerospace_config=home / ".aerospace.toml",
            installed_bundle=(
                home
                / "Library"
                / "Keyboard Layouts"
                / "Adv360Layouts.bundle"
            ),
            local_bin=home / ".local" / "bin",
            support_dir=home / ".local" / "share" / "adv360-host",
            state_dir=state_dir,
            mode_file=state_dir / "mode",
        )


def device_condition(manifest: dict) -> dict:
    return {
        "type": "device_if",
        "identifiers": [
            {
                "description": item["description"],
                "vendor_id": item["vendor_id"],
                "product_id": item["product_id"],
                "is_keyboard": True,
            }
            for item in manifest["devices"]
        ],
    }


def parse_aerospace_shortcuts(config: str) -> set[tuple[frozenset, str]]:
    shortcuts = set()
    for line in config.splitlines():
        match = re.match(r"^\s*([A-Za-z0-9-]+)\s*=", line)
        if not match:
            continue
        parts = match.group(1).lower().split("-")
        modifiers = frozenset(part for part in parts if part in MODIFIER_NAMES)
        keys = [part for part in parts if part not in MODIFIER_NAMES]
        if modifiers in (MEH, HYPER) and len(keys) == 1:
            shortcuts.add((modifiers, keys[0]))
    return shortcuts


def output_modifiers(modifiers: Iterable[str]) -> list[str]:
    return [f"left_{modifier}" for modifier in sorted(modifiers)]


def generate_aerospace_fragment(config: str, manifest: dict) -> dict:
    inverse = {colemak: qwerty for qwerty, colemak in QWERTY_TO_COLEMAK.items()}
    keyboard = device_condition(manifest)
    # Only the physical QWERTY layer sends F24 for the lifetime of the Meh hold.
    manipulators = [{
        "type": "basic",
        "from": {"key_code": "f24", "modifiers": {"optional": ["any"]}},
        "to": [{"set_variable": {
            "name": MEH_QWERTY_VARIABLE,
            "value": 1,
            "key_up_value": 0,
        }}],
        "conditions": [keyboard],
        "description": f"{MANAGED_PREFIX} Track physical QWERTY Meh (F24)",
    }]
    for modifiers, target in sorted(
        parse_aerospace_shortcuts(config),
        key=lambda item: (sorted(item[0]), item[1]),
    ):
        source = inverse.get(target)
        if not source or source == target:
            continue
        mandatory = sorted(
            "command" if modifier == "cmd" else (
                "control" if modifier == "ctrl" else (
                    "option" if modifier == "alt" else modifier
                )
            )
            for modifier in modifiers
        )
        to_modifiers = {
            "command": "left_command",
            "control": "left_control",
            "option": "left_option",
            "shift": "left_shift",
        }
        manipulators.append({
            "type": "basic",
            "from": {
                "key_code": source,
                "modifiers": {"mandatory": mandatory},
            },
            "to": [{
                "key_code": target,
                "modifiers": [
                    to_modifiers[modifier] for modifier in mandatory
                ],
            }],
            "conditions": [
                keyboard,
                {"type": "variable_if", "name": MEH_QWERTY_VARIABLE, "value": 1},
            ],
            "description": (
                f"{MANAGED_PREFIX} AeroSpace "
                f"{'+'.join(mandatory)}: {source} to {target}"
            ),
        })

    return {
        "title": "Adv360 Managed AeroSpace",
        "rules": [{
            "description": (
                f"{MANAGED_PREFIX} Normalize physical QWERTY for AeroSpace"
            ),
            "manipulators": manipulators,
        }],
    }


def selected_karabiner_profile(config: dict) -> dict | None:
    profiles = config.get("profiles", [])
    return next(
        (item for item in profiles if item.get("selected")),
        profiles[0] if profiles else None,
    )


def find_karabiner_device(profile: dict, transport: dict, *, pointing: bool) -> dict | None:
    for entry in profile.get("devices", []):
        identifiers = entry.get("identifiers", {})
        if (
            identifiers.get("vendor_id") == transport["vendor_id"]
            and identifiers.get("product_id") == transport["product_id"]
            and identifiers.get("is_keyboard") is True
            and identifiers.get("is_pointing_device", False) is pointing
            and not any(
                identifiers.get(flag)
                for flag in ("is_consumer", "is_game_pad", "is_virtual_device", "device_address")
            )
        ):
            return entry
    return None


def enable_adv360_composite_devices(profile: dict, manifest: dict) -> None:
    for transport in manifest["devices"]:
        entry = find_karabiner_device(profile, transport, pointing=True)
        if entry is None:
            vendor, product = transport["vendor_id"], transport["product_id"]
            entry = {"identifiers": {
                "vendor_id": vendor,
                "product_id": product,
                "is_keyboard": True,
                "is_pointing_device": True,
            }}
            if (vendor, product) == ADV360_BLUETOOTH:
                legacy = find_karabiner_device(profile, transport, pointing=False)
                if legacy is not None and "simple_modifications" in legacy:
                    entry["simple_modifications"] = copy.deepcopy(legacy["simple_modifications"])
            profile.setdefault("devices", []).append(entry)
        # Karabiner can otherwise ignore all events from the composite device.
        entry["ignore"] = False


def merge_karabiner_config(
    config: dict, fragments: list[dict], *, manifest: dict | None = None
) -> dict:
    result = copy.deepcopy(config)
    profile = selected_karabiner_profile(result)
    if profile is None:
        raise ValueError("Karabiner config has no profiles")
    if manifest is not None:
        enable_adv360_composite_devices(profile, manifest)

    complex_modifications = profile.setdefault("complex_modifications", {})
    rules = complex_modifications.setdefault("rules", [])
    unmanaged = [
        rule
        for rule in rules
        if not rule.get("description", "").startswith(MANAGED_PREFIX)
    ]
    managed = [
        rule
        for fragment in fragments
        for rule in fragment.get("rules", [])
    ]
    # Karabiner stops at the first match. Dedicated Adv360 language and symbol
    # tokens must be decoded before personal rules that reuse the same usages.
    early_managed = [rule for rule in managed if rule["description"] in EARLY_MANAGED_RULES]
    other_managed = [
        rule for rule in managed if rule["description"] not in EARLY_MANAGED_RULES
    ]
    complex_modifications["rules"] = early_managed + unmanaged + other_managed
    return result


def parse_hidutil_devices(output: str) -> set[tuple[int, int]]:
    devices = set()
    for line in output.splitlines():
        match = re.match(
            r"^\s*0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)\s+",
            line,
        )
        if match:
            devices.add((int(match.group(1), 16), int(match.group(2), 16)))
    return devices


def device_gate(
    expected: list[dict], connected: set[tuple[int, int]]
) -> dict[str, bool]:
    return {
        item["description"]: (
            item["vendor_id"], item["product_id"]
        ) in connected
        for item in expected
    }


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".adv360-tmp")
    temporary.write_text(content)
    temporary.replace(path)


def load_manifest(paths: HostPaths) -> dict:
    return load_json(paths.repo_root / "host" / "symbols" / "manifest.json")


def backup(paths: HostPaths) -> Path:
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = paths.state_dir / "backups" / timestamp
    backup_dir.mkdir(parents=True)
    entries = {
        "karabiner": (paths.karabiner_config, "karabiner.json"),
        "bundle": (paths.installed_bundle, "Adv360Layouts.bundle"),
        "mode": (paths.mode_file, "mode"),
    }
    metadata = {"version": 1, "entries": {}}
    for name, (source, relative) in entries.items():
        exists = source.exists()
        metadata["entries"][name] = {
            "existed": exists,
            "relative": relative,
        }
        if not exists:
            continue
        destination = backup_dir / relative
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    (backup_dir / "manifest.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    return backup_dir


def restore(paths: HostPaths, backup_dir: Path) -> None:
    metadata = load_json(backup_dir / "manifest.json")
    destinations = {
        "karabiner": paths.karabiner_config,
        "bundle": paths.installed_bundle,
        "mode": paths.mode_file,
    }
    for name, target in destinations.items():
        entry = metadata["entries"][name]
        source = backup_dir / entry["relative"]
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        if not entry["existed"]:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def compile_host_helpers(paths: HostPaths) -> None:
    sources = paths.repo_root / "host" / "helpers"
    paths.local_bin.mkdir(parents=True, exist_ok=True)
    for source_name, binary_name in (
        ("adv360-input-source.swift", "adv360-input-source"),
        ("adv360-type-unicode.swift", "adv360-type-unicode"),
    ):
        source = sources / source_name
        if not source.is_file():
            raise RuntimeError(f"missing helper source: {source}")
        subprocess.run(
            ["xcrun", "swiftc", "-O", str(source), "-o", str(paths.local_bin / binary_name)],
            check=True,
        )


def install_cli_wrapper(paths: HostPaths) -> None:
    paths.local_bin.mkdir(parents=True, exist_ok=True)
    wrapper = paths.local_bin / "adv360-host"
    script = (
        "#!/bin/sh\n"
        f"exec python3 {str(paths.repo_root / 'host' / 'adv360_host.py')!r} "
        '"$@"\n'
    )
    atomic_write_text(wrapper, script)
    wrapper.chmod(0o755)


def load_fragments(paths: HostPaths, aerospace: str) -> list[dict]:
    fragments = [
        load_json(paths.repo_root / "host" / "karabiner" / name)
        for name in ("adv360-symbols.json", "adv360-language.json")
    ]
    fragments.append(generate_aerospace_fragment(aerospace, load_manifest(paths)))
    return fragments


def install(
    paths: HostPaths,
    connected_devices: set[tuple[int, int]],
    *,
    compile_helpers: bool = True,
) -> Path:
    manifest = load_manifest(paths)
    status = device_gate(manifest["devices"], connected_devices)
    missing = [name for name, present in status.items() if not present]
    if missing:
        raise RuntimeError(
            "unverified Adv360 transport identifiers: " + ", ".join(missing)
        )
    if not paths.karabiner_config.is_file():
        raise RuntimeError(f"missing Karabiner config: {paths.karabiner_config}")

    backup_dir = backup(paths)
    try:
        # AeroSpace is optional. Its existing shortcuts can drive Karabiner remaps.
        aerospace = paths.aerospace_config.read_text() if paths.aerospace_config.is_file() else ""
        config = load_json(paths.karabiner_config)
        merged = merge_karabiner_config(
            config, load_fragments(paths, aerospace), manifest=manifest
        )
        atomic_write_text(
            paths.karabiner_config,
            json.dumps(merged, indent=4, ensure_ascii=False) + "\n",
        )

        source_bundle = (
            paths.repo_root
            / "host"
            / "input-sources"
            / "Adv360Layouts.bundle"
        )
        paths.installed_bundle.parent.mkdir(parents=True, exist_ok=True)
        if paths.installed_bundle.exists():
            shutil.rmtree(paths.installed_bundle)
        shutil.copytree(source_bundle, paths.installed_bundle)

        paths.support_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            paths.support_dir / "adv360-aerospace.json",
            json.dumps(
                generate_aerospace_fragment(aerospace, manifest),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
        )
        paths.state_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(paths.mode_file, "primary\n")
        atomic_write_text(
            paths.state_dir / "last-backup",
            str(backup_dir) + "\n",
        )
        if compile_helpers:
            compile_host_helpers(paths)
            install_cli_wrapper(paths)
    except Exception:
        restore(paths, backup_dir)
        raise
    return backup_dir


def default_source_selector(paths: HostPaths, source_id: str) -> None:
    helper = paths.local_bin / "adv360-input-source"
    if not helper.is_file():
        raise RuntimeError(f"missing input-source helper: {helper}")
    subprocess.run([str(helper), "select", source_id], check=True)


def set_mode(
    paths: HostPaths,
    mode: str,
    selector=None,
) -> None:
    if mode not in ("primary", "fallback"):
        raise ValueError(f"unsupported mode: {mode}")
    if mode == "fallback" and not paths.installed_bundle.is_dir():
        raise RuntimeError("fallback input-source bundle is not installed")
    source_id = PRIMARY_EN if mode == "primary" else FALLBACK_EN
    if selector is None:
        selector = lambda selected: default_source_selector(paths, selected)
    selector(source_id)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(paths.mode_file, mode + "\n")


def verify(
    paths: HostPaths,
    connected_devices: set[tuple[int, int]],
    *,
    require_installed: bool = True,
) -> list[str]:
    problems = []
    manifest = load_manifest(paths)
    status = device_gate(manifest["devices"], connected_devices)
    problems.extend(
        f"device not verified: {name}"
        for name, present in status.items()
        if not present
    )
    if not require_installed:
        return problems

    if not paths.karabiner_config.is_file():
        problems.append("Karabiner config is missing")
    else:
        config = load_json(paths.karabiner_config)
        profile = selected_karabiner_profile(config) or {}
        for transport in manifest["devices"]:
            device = find_karabiner_device(profile, transport, pointing=True)
            if device is None or device.get("ignore") is not False:
                problems.append(f"Karabiner is not modifying events for {transport['description']}")
        rules = profile.get("complex_modifications", {}).get("rules", [])
        if not any(
            rule.get("description", "").startswith(MANAGED_PREFIX)
            for rule in rules
        ):
            problems.append("managed Karabiner rules are missing")
    if not paths.installed_bundle.is_dir():
        problems.append("fallback input-source bundle is missing")
    if not paths.mode_file.is_file():
        problems.append("host mode state is missing")
    for helper in (
        "adv360-host",
        "adv360-input-source",
        "adv360-type-unicode",
    ):
        if not (paths.local_bin / helper).is_file():
            problems.append(f"helper is missing: {helper}")
    input_helper = paths.local_bin / "adv360-input-source"
    if input_helper.is_file() and paths.installed_bundle.is_dir():
        def translate(source_id: str, key_code: int, shifted: bool) -> str:
            command = [
                str(input_helper),
                "translate",
                source_id,
                str(key_code),
            ]
            if shifted:
                command.append("shift")
            result = subprocess.run(
                command,
                check=True,
                text=True,
                capture_output=True,
            )
            return result.stdout.rstrip("\n")

        try:
            problems.extend(
                verify_fallback_symbol_tokens(manifest, translate)
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or "").strip()
            problems.append(
                "fallback input sources are not translatable"
                + (f": {detail}" if detail else "")
            )
    return problems


def verify_fallback_symbol_tokens(manifest: dict, translator) -> list[str]:
    problems = []
    for source_id in (FALLBACK_EN, FALLBACK_RU):
        for symbol in manifest["symbols"]:
            token = symbol["token"]
            shifted = "left_shift" in token.get("modifiers", [])
            actual = translator(
                source_id,
                token["mac_key_code"],
                shifted,
            )
            if actual != symbol["unicode"]:
                problems.append(
                    f"{source_id} token {symbol['name']}: "
                    f"expected {symbol['unicode']!r}, got {actual!r}"
                )
    return problems


def connected_devices_from_system() -> set[tuple[int, int]]:
    override = os.environ.get("ADV360_HIDUTIL_OUTPUT_FILE")
    if override:
        return parse_hidutil_devices(Path(override).read_text())
    result = subprocess.run(
        ["hidutil", "list"],
        check=True,
        text=True,
        capture_output=True,
    )
    return parse_hidutil_devices(result.stdout)


def default_paths() -> HostPaths:
    home = Path(os.environ.get("ADV360_HOME", str(Path.home()))).expanduser()
    return HostPaths.for_home(home, Path(__file__).resolve().parents[1])


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="adv360-host")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("install")
    subparsers.add_parser("verify")
    mode = subparsers.add_parser("mode")
    mode.add_argument("mode", choices=("primary", "fallback"))
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("backup", nargs="?", type=Path)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    paths = default_paths()
    try:
        if args.command == "install":
            backup_dir = install(paths, connected_devices_from_system())
            print(f"installed; backup: {backup_dir}")
        elif args.command == "verify":
            problems = verify(paths, connected_devices_from_system())
            if problems:
                for problem in problems:
                    print(problem, file=sys.stderr)
                return 1
            print("Adv360 host integration verified")
        elif args.command == "mode":
            set_mode(paths, args.mode)
            print(f"mode: {args.mode}")
        elif args.command == "restore":
            backup_dir = args.backup
            if backup_dir is None:
                pointer = paths.state_dir / "last-backup"
                if not pointer.is_file():
                    raise RuntimeError("no recorded backup to restore")
                backup_dir = Path(pointer.read_text().strip())
            restore(paths, backup_dir)
            print(f"restored: {backup_dir}")
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

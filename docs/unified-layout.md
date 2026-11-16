# Unified Advantage360 Pro Layout

This branch contains the Advantage360 Pro firmware and its macOS keyboard
integration. The Russian base is QWERTY and the English base is Colemak-DH.
The symbol layer uses the same physical positions in both. Karabiner can
also normalize keys for existing AeroSpace shortcuts.

## Source of truth

- Edit only `config/adv360.keymap`.
- `config/keymap.json` is obsolete and intentionally removed.
- `host/symbols/manifest.json` is the canonical symbol/token mapping.
- Regenerate host artifacts with `python3 tools/generate_symbols.py`.
- Check generated files with:

```sh
python3 tools/generate_symbols.py --check
python3 tools/generate_symbols.py --validate-artifacts
```

The [Nick Coutsos Keymap Editor][keymap-editor] can open the Advantage360
layout. Build both halves against the pinned ZMK fork before flashing.

## Layers

| Layer | Purpose |
| ---: | --- |
| 0 | Russian physical QWERTY base |
| 1 | English Colemak-DH base |
| 2 | Keypad and media |
| 3 | Function keys |
| 4 | Mod, Bluetooth and bootloader |
| 5 | Symbols on the original key positions |
| 6–7 | Original left and right keyboard arrow layers |
| 8 | Toggleable mouse and browser navigation |
| 9–11 | Precision, fast pointer and scroll overlays |

Hold one of the two small top thumb keys for layer 5. On the left, hold
**35**, directly above the long **Delete** key. On the right, hold **38**,
directly above the long **Enter** key. Both usually carry a **Ctrl** keycap.
[Numbered key diagram](../assets/key-positions.md)

Positions 67 and 68 hold the right and left keyboard arrow layers.
Position 75 toggles mouse navigation.

## Language switching

The lower-left Fn key at position 60 uses the Caps Lock sequence recovered
from the pre-update firmware. It changes the keyboard base between
QWERTY and Colemak-DH. On macOS, enable **Use the Caps Lock key to switch to
and from ABC** and keep stock ABC and Russian–PC enabled. The two switches
should start in sync, since Caps Lock toggles the input source from its
current state. The old layer-only selectors in the symbols and mouse
layers are still available for recovery if they get out of sync.
[Apple Input Sources settings][mac-input-sources]

The two Meh thumb holds use right Control to preserve the existing
Bluetooth mapping of left Control to Command. The QWERTY thumbs send a
held F24 marker so Karabiner can normalize AeroSpace keys from the active
firmware layer even when macOS uses a different input source. On the
right-hand cluster, physical J/K/I/L perform left/down/up/right in both bases.

## Common symbols

The following positions come from the pre-update hardware image. Both
ABC and Russian–PC use the same positions and tap/hold pairs. Letters in the
table identify physical QWERTY key positions.

| Physical keys | Tap in order | Hold differences |
| --- | --- | --- |
| A, S, D, F | `{` `<` `>` `}` | |
| Z, X, C, V | `(` `[` `]` `)` | |
| U, I, O, P | `/` `+` `&` `#` | U → `*`, O → `\|` |
| H, J, K, L, ; | grave accent, `"`, `.`, `=`, `:` | J → `'`, K → `,`, ; → `;` |
| M, comma, period | `!` `-` `@` | M → `?`, comma → `_` |

Each symbol thumb sends an F22 or F23 marker while held. The Karabiner
decoder accepts symbol tokens only during that hold, so regular keypad
digits and operators remain available on the stock macOS input sources.
Extended HID reports must stay enabled. The optional custom input-source
pair decodes tokens directly and is not needed for the stock pair.

## Mouse and navigation

Tap the bottom-right key (position **75**) to toggle the mouse layer. The
right-hand cursor cluster and direct scroll keys stay active until you
tap it again. QWERTY letters below refer to physical positions.

| Action | Key with the mouse layer on |
| --- | --- |
| Pointer up, left, down, right | Right-hand `I`, `J`, `K`, `L` (24, 41, 42, 43) |
| Direct vertical scroll | `M` up, `.` down (55, 57) |
| Direct horizontal scroll | `U` left, `O` right (23, 25) |
| Precision (⅓ speed) | Hold `G` (33) while moving |
| Fast movement (2½× speed) | Hold `T` (19) while moving |
| Four-way scroll on the cursor cluster | Hold `B` (51) and use `I/J/K/L` |
| Left click or drag | Right thumb **70** |
| Right click | Right thumb **69** |
| Back, previous tab, next tab, forward | `Q/W/E/R` (15–18) in Safari |

Normal pointer movement ramps up for 500 ms to a firmware target of 1400
HID units per second. The configured macOS pointer speed affects the actual
distance.

## Host integration

The installer creates a timestamped backup and replaces Karabiner rules whose
description starts with `[Adv360 Managed]`. It preserves personal
`simple_modifications`. If `~/.aerospace.toml` exists, the installer reads
it to generate the keyboard's position remaps. The AeroSpace config is
used read-only.

The first install is bootstrapped from the repository:

```sh
python3 host/adv360_host.py install
```

Installation intentionally stops unless both the real USB and Bluetooth
Kinesis identifiers are visible. Do not bypass that gate. After installation,
ensure `~/.local/bin` is on `PATH` and use:

```sh
adv360-host verify
adv360-host mode primary
adv360-host mode fallback
adv360-host restore
adv360-host restore ~/.local/state/adv360-host/backups/TIMESTAMP
```

`mode primary` selects stock ABC and keeps RussianWin as its paired Russian
source. `mode fallback` selects the installed custom pair without reflashing.
`restore` uses the last recorded backup unless a backup directory is supplied.

The fallback bundle is installed at
`~/Library/Keyboard Layouts/Adv360Layouts.bundle`. A login cycle may be needed
before macOS exposes newly installed input-source IDs.

## Build, flash, and rollback

GitHub Actions builds both halves and publishes `firmware-no-clique`. The
repository also supports the upstream local-container `make` workflow. The
firmware must compile against the revision pinned in `config/west.yml`.

Before flashing, verify the generated artifacts and host rules:

```sh
python3 -m unittest discover -s tests -v
python3 tools/generate_symbols.py --check
python3 tools/generate_symbols.py --validate-artifacts
python3 tools/generate_aerospace_rules.py --config ~/.aerospace.toml --check
karabiner_cli --lint-complex-modifications 'host/karabiner/*.json'
```

The local build on 2026-11-16 used ZMK `f1d5fc7`, Zephyr `dacab4875df7`, and
Zephyr SDK 0.16.9. Both builds succeeded and the flash helper checked the UF2
format and the embedded product strings for each side. The newer toolchain
produced files with different hashes from the June build.

| Purpose | File | SHA-256 |
| --- | --- | --- |
| Current left | `firmware/adv360-restored-left.uf2` | `8000b81c09db87e73ee0e554370994c7b72e928ee608c354422c0a93fe1f2378` |
| Current right | `firmware/adv360-restored-right.uf2` | `80cb1683c2bf9cb0120651dabe835762d25ab68b1711ce7d2e8d71b6c72ddcfe` |
| Recovery left | `firmware/hardware-recovery-left.uf2` | `420277bcef59f05611e3db31699ef857994ee78d823632eaafdb87dfbfe78e06` |
| Recovery right | `firmware/hardware-recovery-right.uf2` | `b8f91658abf0abb5cdb0ea5deed355f9dc3d5629d81723adc968c6fe19cadf95` |

The recovery files contain the original application bytes taken from the
pre-update hardware snapshots. The raw `hardware-before-20261116-*.uf2`
files also contain other regions. Use the listed recovery pair to roll back
and keep the raw snapshots as recovery sources.

Use the [macOS flash helper](flash-macos.md) to install a pair over USB with
the Kinesis bootloader shortcuts.

### Symbols over Bluetooth

If symbols work by USB but fail over Bluetooth after updating, connect the
left module by USB so it is available during troubleshooting. In macOS,
open **System Settings → Bluetooth → Adv360 Pro → Details → Disconnect**.
Wait for the keyboard to reconnect or select **Connect**. This fixed the
cached HID descriptor on the tested Mac and raised its observed usage
limit from 103 (`0x67`) to 151 (`0x97`). The newer descriptor covers F22
and F23, which the symbol layer uses while a thumb is held.

If Bluetooth still lacks the extended descriptor, clear the active
keyboard pairing with **Mod + Right Windows**, forget Adv360 Pro in
macOS Bluetooth settings, and pair it again. This is a pairing recovery
step. [Kinesis Bluetooth troubleshooting](https://kinesis-ergo.com/support/kb360pro/)

## Hardware acceptance

1. Confirm F22/F23, the QWERTY Meh marker F24, and every used symbol token over
   both USB and Bluetooth.
2. Check the original symbol tap/hold pairs in stock ABC and RussianWin.
3. Check `cc`, `xx`, `vv`/`dd`, fast rolls, and single/chorded home-row mods.
4. Check the arrow layers, normal pointer speed, precision, acceleration,
   direct and four-way scrolling, and drag.
5. Check every used AeroSpace Meh/Hyper binding in RU and EN, including focus,
   move, workspace, layout, resize, and service mode.
6. Record any single timing or speed calibration before changing defaults.

[keymap-editor]: https://nickcoutsos.github.io/keymap-editor/
[mac-input-sources]: https://support.apple.com/en-hk/guide/mac-help/mchl84525d76/27/mac/27

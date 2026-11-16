import CoreGraphics
import Foundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

let arguments = Array(CommandLine.arguments.dropFirst())
let dryRun: Bool
let value: String

if arguments.count == 1 {
    dryRun = false
    value = arguments[0]
} else if arguments.count == 2 && arguments[0] == "--dry-run" {
    dryRun = true
    value = arguments[1]
} else {
    fail("usage: adv360-type-unicode [--dry-run] HEX_CODEPOINT")
}

guard
    let codepoint = UInt32(value, radix: 16),
    let scalar = UnicodeScalar(codepoint)
else {
    fail("invalid Unicode codepoint: \(value)")
}

let text = String(scalar)
if dryRun {
    print(text)
    exit(0)
}

guard
    let source = CGEventSource(stateID: .hidSystemState),
    let down = CGEvent(
        keyboardEventSource: source,
        virtualKey: 0,
        keyDown: true
    ),
    let up = CGEvent(
        keyboardEventSource: source,
        virtualKey: 0,
        keyDown: false
    )
else {
    fail("unable to create keyboard event")
}

var utf16 = Array(text.utf16)
down.keyboardSetUnicodeString(
    stringLength: utf16.count,
    unicodeString: &utf16
)
up.keyboardSetUnicodeString(
    stringLength: utf16.count,
    unicodeString: &utf16
)
down.post(tap: .cghidEventTap)
up.post(tap: .cghidEventTap)

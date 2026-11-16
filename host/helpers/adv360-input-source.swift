import Carbon
import Foundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

func allInputSources() -> [TISInputSource] {
    let sources = TISCreateInputSourceList(nil, true).takeRetainedValue()
    return sources as NSArray as! [TISInputSource]
}

func inputSourceID(_ source: TISInputSource) -> String? {
    guard let pointer = TISGetInputSourceProperty(
        source,
        kTISPropertyInputSourceID
    ) else {
        return nil
    }
    return Unmanaged<CFString>
        .fromOpaque(pointer)
        .takeUnretainedValue() as String
}

func findInputSource(_ identifier: String) -> TISInputSource? {
    return allInputSources().first {
        inputSourceID($0) == identifier
    }
}

func translate(
    _ source: TISInputSource,
    keyCode: UInt16,
    shifted: Bool
) -> String {
    guard let pointer = TISGetInputSourceProperty(
        source,
        kTISPropertyUnicodeKeyLayoutData
    ) else {
        fail("input source has no Unicode keyboard layout data")
    }
    let data = Unmanaged<CFData>
        .fromOpaque(pointer)
        .takeUnretainedValue()
    guard let bytes = CFDataGetBytePtr(data) else {
        fail("input source keyboard layout data is empty")
    }
    let layout = UnsafeRawPointer(bytes)
        .assumingMemoryBound(to: UCKeyboardLayout.self)
    var deadKeyState: UInt32 = 0
    var length = 0
    var characters = [UniChar](repeating: 0, count: 16)
    let modifierState = shifted ? UInt32(shiftKey >> 8) : 0
    let status = UCKeyTranslate(
        layout,
        keyCode,
        UInt16(kUCKeyActionDown),
        modifierState,
        UInt32(LMGetKbdType()),
        OptionBits(kUCKeyTranslateNoDeadKeysBit),
        &deadKeyState,
        characters.count,
        &length,
        &characters
    )
    guard status == noErr else {
        fail("UCKeyTranslate failed: \(status)")
    }
    return String(
        decoding: characters.prefix(Int(length)),
        as: UTF16.self
    )
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard let command = arguments.first else {
    fail("usage: adv360-input-source list|enable ID|select ID|translate ID KEYCODE [shift]")
}

switch command {
case "list":
    guard arguments.count == 1 else {
        fail("usage: adv360-input-source list")
    }
    let identifiers = Set(allInputSources().compactMap(inputSourceID))
    for identifier in identifiers.sorted() {
        print(identifier)
    }
case "enable", "select":
    guard arguments.count == 2 else {
        fail("usage: adv360-input-source \(command) ID")
    }
    let identifier = arguments[1]
    guard let source = findInputSource(identifier) else {
        fail("input source not found: \(identifier)")
    }
    let enableStatus = TISEnableInputSource(source)
    guard enableStatus == noErr else {
        fail("unable to enable input source \(identifier): \(enableStatus)")
    }
    if command == "select" {
        let selectStatus = TISSelectInputSource(source)
        guard selectStatus == noErr else {
            fail("unable to select input source \(identifier): \(selectStatus)")
        }
    }
case "translate":
    guard arguments.count == 3 || arguments.count == 4 else {
        fail("usage: adv360-input-source translate ID KEYCODE [shift]")
    }
    let identifier = arguments[1]
    guard let keyCode = UInt16(arguments[2]) else {
        fail("invalid virtual key code: \(arguments[2])")
    }
    let shifted = arguments.count == 4 && arguments[3] == "shift"
    if arguments.count == 4 && !shifted {
        fail("unknown modifier: \(arguments[3])")
    }
    guard let source = findInputSource(identifier) else {
        fail("input source not found: \(identifier)")
    }
    print(translate(source, keyCode: keyCode, shifted: shifted))
default:
    fail("usage: adv360-input-source list|enable ID|select ID|translate ID KEYCODE [shift]")
}

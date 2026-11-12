import AppKit
import ApplicationServices
import Foundation

struct ProbeFailure: Error, CustomStringConvertible {
    let description: String
    init(_ description: String) { self.description = description }
}

func check(_ condition: Bool, _ message: String) throws {
    if !condition { throw ProbeFailure(message) }
}

func wait<T>(_ label: String, seconds: Double = 45, _ observe: () throws -> T?) throws -> T {
    let deadline = ProcessInfo.processInfo.systemUptime + seconds
    while ProcessInfo.processInfo.systemUptime < deadline {
        if let result = try observe() { return result }
        Thread.sleep(forTimeInterval: 0.2)
    }
    throw ProbeFailure("Timed out waiting for \(label)")
}

func attribute(_ node: AXUIElement, _ name: String) -> CFTypeRef? {
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(node, name as CFString, &value) == .success ? value : nil
}

func match(_ root: AXUIElement, label: String, role: String?, enabled: Bool) -> AXUIElement? {
    return walk(root) { node in
        guard role == nil || attribute(node, kAXRoleAttribute) as? String == role else { return false }
        return [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute].contains { name in
            attribute(node, name) as? String == label &&
                (!enabled || attribute(node, kAXEnabledAttribute) as? Bool == true)
        }
    }
}

func visible(
    _ process: Process, _ label: String, role: String? = nil, enabled: Bool = false
) throws -> AXUIElement {
    let application = AXUIElementCreateApplication(process.processIdentifier)
    AXUIElementSetMessagingTimeout(application, 2)
    return try wait(label) {
        try check(process.isRunning, "Installed Desktop exited before UI readiness")
        guard let windows = attribute(application, kAXWindowsAttribute) as? [AXUIElement] else {
            return nil
        }
        for window in windows {
            if let element = match(window, label: label, role: role, enabled: enabled) { return element }
        }
        return nil
    }
}

func press(_ node: AXUIElement) throws {
    try check(
        AXUIElementPerformAction(node, kAXPressAction as CFString) == .success,
        "Installed UI did not accept the accessibility action"
    )
}

func settings(_ process: Process) throws {
    try press(visible(process, "Settings", role: "AXLink"))
    _ = try visible(process, "Local workspace")
}

func close(_ process: Process) throws {
    let application = NSRunningApplication(processIdentifier: process.processIdentifier)
    try check(application?.terminate() == true, "Installed Desktop refused normal termination")
    _ = try wait("Desktop termination", seconds: 15) { process.isRunning ? nil : true }
}

func launch(_ executable: URL) throws -> Process {
    let process = Process()
    process.executableURL = executable
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    try process.run()
    return process
}

func native(_ cli: URL, _ arguments: [String]) throws -> [String: Any] {
    let process = Process()
    process.executableURL = cli
    process.arguments = arguments + ["--json"]
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = FileHandle.nullDevice
    try process.run()
    defer { if process.isRunning { process.terminate() } }
    _ = try wait("bundled CLI readback", seconds: 30) { process.isRunning ? nil : true }
    try check(process.terminationStatus == 0, "Installed CLI readback failed")
    let payload = try JSONSerialization.jsonObject(with: pipe.fileHandleForReading.readDataToEndOfFile())
    guard let envelope = payload as? [String: Any], envelope["ok"] as? Bool == true,
        let data = envelope["data"] as? [String: Any]
    else { throw ProbeFailure("Installed CLI reply has an unsupported shape") }
    return data
}


struct Review {
    let raw: String
    let digest: String
    let context: [String: Any]
    let action: String
}

struct Catalogs {
    let directory: URL
    let languages: [String: [String: String]]

    init(_ directory: URL) throws {
        self.directory = directory
        let bytes = try Data(contentsOf: directory.deletingLastPathComponent().appendingPathComponent("localization.json"))
        guard let configuration = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
            let languages = configuration["languages"] as? [String: [String: String]]
        else { throw ProbeFailure("Language configuration is unavailable") }
        self.languages = languages
    }

    func text(_ key: String, _ locale: String = "en") throws -> String {
        let bytes = try Data(contentsOf: directory.appendingPathComponent(locale + ".json"))
        guard let catalog = try JSONSerialization.jsonObject(with: bytes) as? [String: String],
            let text = catalog[key]
        else { throw ProbeFailure("A required packaged message is unavailable") }
        return text
    }

    func name(_ locale: String) throws -> String {
        guard let language = languages[locale], let name = language["name"] else {
            throw ProbeFailure("Unknown packaged language")
        }
        if locale == "kk", let shortName = language["shortName"] { return name + " · " + shortName }
        return name
    }
}

func walk(_ root: AXUIElement, _ accept: (AXUIElement) -> Bool) -> AXUIElement? {
    var nodes = [root]
    for _ in 0..<2500 {
        guard let node = nodes.popLast() else { break }
        if accept(node) { return node }
        if let children = attribute(node, kAXChildrenAttribute) as? [AXUIElement] {
            nodes.append(contentsOf: children.reversed())
        }
    }
    return nil
}

func application(_ process: Process) -> AXUIElement {
    let application = AXUIElementCreateApplication(process.processIdentifier)
    AXUIElementSetMessagingTimeout(application, 2)
    return application
}

func pressNamed(_ process: Process, _ label: String, role: String? = nil) throws {
    var node = try visible(process, label, role: role, enabled: role != nil)
    for _ in 0..<4 {
        var actions: CFArray?
        if AXUIElementCopyActionNames(node, &actions) == .success,
            let names = actions as? [String], names.contains(kAXPressAction) {
            try press(node)
            return
        }
        guard let parent = attribute(node, kAXParentAttribute) else { break }
        try check(CFGetTypeID(parent) == AXUIElementGetTypeID(), "Unsupported accessibility parent")
        node = (parent as! AXUIElement)
    }
    throw ProbeFailure("Named UI control does not expose a press action")
}

func focus(_ process: Process, _ node: AXUIElement) throws {
    try check(AXUIElementSetAttributeValue(application(process), kAXFrontmostAttribute as CFString, kCFBooleanTrue) == .success,
        "Owned application could not become frontmost")
    try check(AXUIElementSetAttributeValue(node, kAXFocusedAttribute as CFString, kCFBooleanTrue) == .success,
        "Owned UI control could not receive keyboard focus")
    _ = try wait("owned keyboard focus") {
        try check(process.isRunning, "Installed Desktop exited before keyboard input")
        return NSWorkspace.shared.frontmostApplication?.processIdentifier == process.processIdentifier &&
            attribute(node, kAXFocusedAttribute) as? Bool == true ? true : nil
    }
}

func key(_ process: Process, _ code: CGKeyCode, flags: CGEventFlags = []) throws {
    try check(process.isRunning && NSWorkspace.shared.frontmostApplication?.processIdentifier == process.processIdentifier,
        "Keyboard input lost its owned application")
    guard let down = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: true),
        let up = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: false)
    else { throw ProbeFailure("Native keyboard events are unavailable") }
    down.flags = flags
    up.flags = []
    down.post(tap: .cghidEventTap)
    up.post(tap: .cghidEventTap)
}

func enter(_ process: Process, _ field: AXUIElement, _ value: String) throws {
    try focus(process, field)
    try key(process, 0, flags: .maskCommand)
    for scalar in value.unicodeScalars {
        try check(process.isRunning && NSWorkspace.shared.frontmostApplication?.processIdentifier == process.processIdentifier,
            "Keyboard input lost its owned application")
        var characters = Array(String(scalar).utf16)
        guard let down = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: true),
            let up = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: false)
        else { throw ProbeFailure("Native text entry is unavailable") }
        down.flags = []
        up.flags = []
        down.keyboardSetUnicodeString(stringLength: characters.count, unicodeString: &characters)
        down.post(tap: .cghidEventTap)
        up.post(tap: .cghidEventTap)
    }
    _ = try wait("entered context label") {
        attribute(field, kAXValueAttribute) as? String == value ? true : nil
    }
}

func review(_ process: Process, _ catalogs: Catalogs, _ locale: String) throws -> Review {
    let region = try visible(process, catalogs.text("profiles.reviewNativeProfilePlan", locale))
    var observation = "not observed"
    do {
        return try wait("exact public context plan") {
            var document: [String: Any]?
            var raw: String?
            var digest: String?
            var nodes = 0, strings = 0, jsonValues = 0
            var roles: [String: Int] = [:]
            _ = walk(region) { node in
                nodes += 1
                let role = attribute(node, kAXRoleAttribute) as? String ?? "unknown"
                roles[role, default: 0] += 1
                for name in [kAXValueAttribute, kAXTitleAttribute, kAXDescriptionAttribute] {
                    guard let value = attribute(node, name) as? String, value.utf8.count <= 65536 else { continue }
                    strings += 1
                    if value.range(of: "^sha256:[0-9a-f]{64}$", options: .regularExpression) != nil { digest = value }
                    if let bytes = value.data(using: .utf8),
                        let object = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] {
                        jsonValues += 1
                        if let change = object["change"] as? [String: Any], change["context"] is [String: Any] {
                            document = change
                            raw = value
                        }
                    }
                }
                return false
            }
            let roleSummary = roles.keys.sorted().map { "\($0)=\(roles[$0]!)" }.joined(separator: ",")
            observation = "nodes=\(nodes), strings=\(strings), JSON=\(jsonValues), plan=\(raw != nil), digest=\(digest != nil), roles=[\(roleSummary)]"
            guard let change = document, let raw = raw, let digest = digest,
                let context = change["context"] as? [String: Any], let action = change["action"] as? String
            else { return nil }
            return Review(raw: raw, digest: digest, context: context, action: action)
        }
    } catch {
        throw ProbeFailure("\(error); native review observation: \(observation)")
    }
}

func validate(_ review: Review, _ action: String, _ label: String, _ identifier: String? = nil) throws -> String {
    guard review.action == action, review.context["label"] as? String == label,
        let authority = review.context["authority"] as? [String: Any], authority["kind"] as? String == "local",
        let id = review.context["context_id"] as? String, !id.isEmpty, id.utf8.count <= 512
    else { throw ProbeFailure("Displayed context plan changed intent or authority") }
    if let expected = identifier { try check(id == expected, "Displayed context plan changed identity") }
    return id
}

func confirm(_ process: Process, _ catalogs: Catalogs) throws {
    let confirmation = try visible(process, catalogs.text("profiles.iReviewedThisExactPlanAndAuthorizeThisLocal"), role: kAXCheckBoxRole)
    try check((attribute(confirmation, kAXValueAttribute) as? NSNumber)?.intValue == 0,
        "Context review was already confirmed")
    let apply = try visible(process, catalogs.text("profiles.applyReviewedChange"), role: kAXButtonRole)
    try check(attribute(apply, kAXEnabledAttribute) as? Bool == false, "Unconfirmed context review was applicable")
    try press(confirmation)
    try press(visible(process, catalogs.text("profiles.applyReviewedChange"), role: kAXButtonRole, enabled: true))
    _ = try wait("context review completion") {
        try check(process.isRunning, "Installed Desktop exited during context apply")
        return match(application(process), label: try catalogs.text("profiles.reviewNativeProfilePlan"), role: nil, enabled: false) == nil ? true : nil
    }
}

func context(_ process: Process, _ catalogs: Catalogs, _ label: String) throws -> Review {
    let field = try visible(process, catalogs.text("profiles.contextLabel"), role: kAXTextFieldRole, enabled: true)
    try enter(process, field, label)
    try pressNamed(process, catalogs.text("profiles.reviewContextCreation"), role: kAXButtonRole)
    try pressNamed(process, catalogs.text("profiles.exactPublicPlan"), role: kAXDisclosureTriangleRole)
    let retained = try review(process, catalogs, "en")
    _ = try validate(retained, "create", label)
    return retained
}

func savedContexts(_ cli: URL) throws -> [String: Any] {
    let result = try native(cli, ["context", "list"])
    try check(result["contexts"] is [[String: Any]], "Native context list has an unsupported shape")
    return result
}

func selected(_ cli: URL, _ identifier: String) throws {
    _ = try wait("selected native context") {
        let result = try savedContexts(cli)
        return (result["selected"] as? [String: Any])?["context_id"] as? String == identifier ? true : nil
    }
}

func selectContext(_ process: Process, _ cli: URL, _ catalogs: Catalogs, _ label: String, _ identifier: String) throws {
    try pressNamed(process, catalogs.text("profiles.reviewViewSelection"), role: kAXButtonRole)
    try pressNamed(process, catalogs.text("profiles.exactPublicPlan"), role: kAXDisclosureTriangleRole)
    _ = try validate(review(process, catalogs, "en"), "select", label, identifier)
    try confirm(process, catalogs)
    try selected(cli, identifier)
    _ = try visible(process, label + catalogs.text("profiles.selectedView"))
}

func language(_ process: Process, _ catalogs: Catalogs, _ previous: String, _ next: String) throws {
    let selector = try visible(process, catalogs.text("language.label", previous), role: kAXPopUpButtonRole, enabled: true)
    let expected = try catalogs.name(next)
    if attribute(selector, kAXValueAttribute) as? String != expected {
        try press(selector)
        let option = try wait("packaged native language option") {
            match(application(process), label: try catalogs.name(next), role: kAXMenuItemRole, enabled: true)
        }
        try press(option)
    }
    _ = try visible(process, catalogs.text("language.label", next), role: kAXPopUpButtonRole, enabled: true)
}

func theme(_ process: Process, _ catalogs: Catalogs, _ locale: String, _ dark: Bool) throws {
    let desiredLabel = try catalogs.text(dark ? "shell.light" : "shell.dark", locale)
    if match(application(process), label: desiredLabel, role: kAXButtonRole, enabled: true) == nil {
        try pressNamed(process, catalogs.text(dark ? "shell.dark" : "shell.light", locale), role: kAXButtonRole)
    }
    _ = try visible(process, desiredLabel, role: kAXButtonRole, enabled: true)
    _ = try visible(process, catalogs.text("language.label", locale), role: kAXPopUpButtonRole, enabled: true)
}

func sidebar(_ process: Process, _ catalogs: Catalogs, _ locale: String) throws {
    _ = try wait("native sidebar direction") { () throws -> Bool? in
        let control = try visible(process, catalogs.text("language.label", locale), role: kAXPopUpButtonRole, enabled: true)
        guard let windows = attribute(application(process), kAXWindowsAttribute) as? [AXUIElement], let window = windows.first,
            let controlPosition = attribute(control, kAXPositionAttribute), let controlSize = attribute(control, kAXSizeAttribute),
            let windowPosition = attribute(window, kAXPositionAttribute), let windowSize = attribute(window, kAXSizeAttribute)
        else { return nil }
        var point = CGPoint.zero, origin = CGPoint.zero
        var size = CGSize.zero, frame = CGSize.zero
        for (value, expected) in [(controlPosition, AXValueType.cgPoint), (controlSize, .cgSize),
            (windowPosition, .cgPoint), (windowSize, .cgSize)] {
            try check(CFGetTypeID(value) == AXValueGetTypeID() && AXValueGetType((value as! AXValue)) == expected,
                "Native layout geometry has an unsupported shape")
        }
        _ = AXValueGetValue((controlPosition as! AXValue), .cgPoint, &point)
        _ = AXValueGetValue((controlSize as! AXValue), .cgSize, &size)
        _ = AXValueGetValue((windowPosition as! AXValue), .cgPoint, &origin)
        _ = AXValueGetValue((windowSize as! AXValue), .cgSize, &frame)
        guard size.width > 0, frame.width > 0 else { return nil }
        let right = point.x + size.width / 2 > origin.x + frame.width / 2
        return right == (catalogs.languages[locale]?["direction"] == "rtl") ? true : nil
    }
}

func personal(_ process: Process, _ cli: URL, _ catalogs: Catalogs) throws -> (String, Bool, Int) {
    try pressNamed(process, catalogs.text("shell.connections"), role: "AXLink")
    _ = try visible(process, catalogs.text("profiles.connectionsAndContexts"))
    let initialDark = match(application(process), label: try catalogs.text("shell.light"), role: kAXButtonRole, enabled: true) != nil
    let first = try context(process, catalogs, "Native personal one")
    let firstID = try validate(first, "create", "Native personal one")
    var locale = "en"
    var combinations = 0
    for dark in [false, true] {
        try theme(process, catalogs, locale, dark)
        for next in catalogs.languages.keys.sorted() {
            try language(process, catalogs, locale, next)
            locale = next
            try sidebar(process, catalogs, locale)
            let current = try review(process, catalogs, locale)
            try check(current.raw == first.raw && current.digest == first.digest, "Appearance changes replaced the retained context plan")
            let field = try visible(process, catalogs.text("profiles.contextLabel", locale), role: kAXTextFieldRole, enabled: true)
            try check(attribute(field, kAXValueAttribute) as? String == "Native personal one", "Language change replaced entered context text")
            let checkbox = try visible(process, catalogs.text("profiles.iReviewedThisExactPlanAndAuthorizeThisLocal", locale), role: kAXCheckBoxRole)
            try check((attribute(checkbox, kAXValueAttribute) as? NSNumber)?.intValue == 0, "Appearance changes confirmed a context review")
            combinations += 1
        }
    }
    try language(process, catalogs, locale, "en")
    try confirm(process, catalogs)
    let second = try context(process, catalogs, "Native personal two")
    let secondID = try validate(second, "create", "Native personal two")
    try check(firstID != secondID, "Native contexts share an identity")
    try confirm(process, catalogs)
    let discarded = try context(process, catalogs, "Native dismissed context")
    _ = try validate(discarded, "create", "Native dismissed context")
    try pressNamed(process, catalogs.text("profiles.dismissReview"), role: kAXButtonRole)
    let listed = try savedContexts(cli)
    guard let rows = listed["contexts"] as? [[String: Any]] else { throw ProbeFailure("Native contexts are unavailable") }
    let identifiers = rows.compactMap { ($0["context"] as? [String: Any])?["context_id"] as? String }
    try check(Set(identifiers) == Set([firstID, secondID]) && rows.count == 2, "Dismissed context review changed native records")
    try selectContext(process, cli, catalogs, "Native personal one", firstID)
    try selectContext(process, cli, catalogs, "Native personal two", secondID)
    try theme(process, catalogs, "en", !initialDark)
    try language(process, catalogs, "en", "ar")
    return (secondID, !initialDark, combinations)
}

func prove() throws {
    let environment = ProcessInfo.processInfo.environment
    try check(environment["GITHUB_ACTIONS"] == "true" && environment["RUNNER_ENVIRONMENT"] == "github-hosted" && environment["RUNNER_OS"] == "macOS",
        "A disposable hosted macOS runner is required")
    try check(AXIsProcessTrusted(), "Hosted macOS accessibility client lacks authorization")
    try check(CGPreflightPostEventAccess(), "Hosted macOS keyboard client lacks authorization")
    let arguments = CommandLine.arguments
    try check(arguments.count == 4, "Installed executable, CLI and message catalog paths are required")
    let app = URL(fileURLWithPath: arguments[1])
    let cli = URL(fileURLWithPath: arguments[2])
    let catalogs = try Catalogs(URL(fileURLWithPath: arguments[3]))
    let version = try native(cli, ["version"])
    guard version["runtime"] as? String == "rust", version["wire_schema_version"] as? Int == 1,
        let cliVersion = version["cli_version"] as? String
    else { throw ProbeFailure("Installed CLI version contract differs") }
    let doctor = try native(cli, ["doctor"])
    let checks = doctor["checks"] as? [[String: Any]] ?? []
    try check(checks.contains {
        $0["name"] as? String == "local_identity" && $0["state"] as? String == "needs_user_action"
    }, "First-run macOS workspace is required")

    var process = try launch(app)
    defer { if process.isRunning { process.terminate() } }
    _ = try visible(process, "Engine \(cliVersion)")
    try settings(process)
    guard let fixture = ProcessInfo.processInfo.environment["XDG_DATA_HOME"] else {
        throw ProbeFailure("An isolated XDG data directory is required")
    }
    _ = try visible(process, fixture + "/ai-stp")
    try press(visible(process,
        "Initialize or resume this device using the selected credential storage.", role: kAXCheckBoxRole))
    try press(visible(process, "Initialize workspace", role: kAXButtonRole, enabled: true))
    fputs("Invoked enabled workspace initialization\n", stderr)
    do {
        _ = try visible(process, "Initialized")
    } catch {
        if let report = try? native(cli, ["doctor"]), let checks = report["checks"] as? [[String: Any]] {
            let ready = checks.contains {
                $0["name"] as? String == "local_identity" && $0["state"] as? String == "ready"
            }
            fputs("Independent local identity ready: \(ready)\n", stderr)
        }
        throw error
    }
    let identity = try JSONSerialization.data(withJSONObject: native(cli, ["device", "show"]), options: [.sortedKeys])
    let (selectedID, dark, combinations) = try personal(process, cli, catalogs)
    try check(combinations == catalogs.languages.count * 2, "Native appearance cases are incomplete")
    try close(process)
    fputs("Restarting the initialized workspace\n", stderr)
    process = try launch(app)
    _ = try visible(process, catalogs.text("language.label", "ar"), role: kAXPopUpButtonRole, enabled: true)
    _ = try visible(process, catalogs.text(dark ? "shell.light" : "shell.dark", "ar"), role: kAXButtonRole, enabled: true)
    try sidebar(process, catalogs, "ar")
    try selected(cli, selectedID)
    try language(process, catalogs, "ar", "en")
    let link = try visible(process, catalogs.text("shell.connections"), role: "AXLink", enabled: true)
    try focus(process, link)
    try key(process, 36)
    _ = try visible(process, catalogs.text("profiles.connectionsAndContexts"))
    _ = try visible(process, "Native personal two" + catalogs.text("profiles.selectedView"))
    let listed = try savedContexts(cli)
    try check((listed["contexts"] as? [[String: Any]])?.count == 2, "Restart lost native context records")
    try settings(process)
    _ = try visible(process, "Initialized")
    let restarted = try JSONSerialization.data(withJSONObject: native(cli, ["device", "show"]), options: [.sortedKeys])
    try check(identity == restarted, "Installed device identity changed after restart")
    try close(process)
    let result: [String: Any] = [
        "cli_version": cliVersion,
        "theme_locale_observations": combinations,
        "personal_controls": [
            "native_vault_initialization": true,
            "two_native_offline_contexts": true,
            "exact_context_plan_and_explicit_confirmation": true,
            "dismissed_review_has_no_effect": true,
            "native_keyboard_text_and_navigation": true,
            "theme_locale_changes_preserve_fields_and_review": true,
            "rtl_sidebar_mirrors": true,
            "selected_context_survives_restart": true,
            "theme_and_locale_survive_restart": true,
            "device_identity_survives_restart": true,
        ],
    ]
    let output = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    print(String(decoding: output, as: UTF8.self))
}

do {
    try prove()
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}

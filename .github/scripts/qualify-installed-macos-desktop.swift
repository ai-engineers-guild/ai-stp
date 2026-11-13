import AppKit
import ApplicationServices
import Foundation

struct ProbeFailure: Error, CustomStringConvertible {
    let description: String
    let sourceLine: Int
    init(_ description: String, line: Int = #line) {
        self.description = description
        self.sourceLine = line
    }
}

func check(_ condition: Bool, _ message: String, line: Int = #line) throws {
    if !condition { throw ProbeFailure(message, line: line) }
}

func wait<T>(_ label: String, seconds: Double = 45, line: Int = #line, _ observe: () throws -> T?) throws -> T {
    let deadline = ProcessInfo.processInfo.systemUptime + seconds
    while ProcessInfo.processInfo.systemUptime < deadline {
        if let result = try observe() { return result }
        RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.2))
    }
    throw ProbeFailure("Timed out waiting for \(label)", line: line)
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
    _ process: Process, _ label: String, role: String? = nil, enabled: Bool = false, line: Int = #line
) throws -> AXUIElement {
    let application = AXUIElementCreateApplication(process.processIdentifier)
    AXUIElementSetMessagingTimeout(application, 2)
    return try wait(label, line: line) {
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

func press(_ node: AXUIElement, line: Int = #line) throws {
    try check(
        AXUIElementPerformAction(node, kAXPressAction as CFString) == .success,
        "Installed UI did not accept the accessibility action", line: line
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

func normalWorkArea(_ process: Process, phase: String = "initial") throws -> CGSize {
    var snapshot: [String: Any] = [:]
    do {
        return try wait("normal native window within display work area") {
            guard let windows = attribute(application(process), kAXWindowsAttribute) as? [AXUIElement],
                windows.count == 1, let window = windows.first,
                let position = attribute(window, kAXPositionAttribute),
                let size = attribute(window, kAXSizeAttribute),
                let primary = NSScreen.screens.first
            else { return nil }
            try check(CFGetTypeID(position) == AXValueGetTypeID() &&
                CFGetTypeID(size) == AXValueGetTypeID(), "Native window geometry is unavailable")
            var point = CGPoint.zero
            var extent = CGSize.zero
            try check(AXValueGetValue((position as! AXValue), .cgPoint, &point) &&
                AXValueGetValue((size as! AXValue), .cgSize, &extent),
                "Native window geometry could not be read")
            snapshot["window_count"] = windows.count
            snapshot["frame"] = [
                "x": Double(point.x), "y": Double(point.y),
                "width": Double(extent.width), "height": Double(extent.height),
            ]
            snapshot["work_areas"] = NSScreen.screens.map { screen in
                let visible = screen.visibleFrame
                return [
                    "x": Double(visible.minX), "y": Double(primary.frame.maxY - visible.maxY),
                    "width": Double(visible.width), "height": Double(visible.height),
                    "scale_factor": Double(screen.backingScaleFactor),
                ]
            }
            let frame = CGRect(origin: point, size: extent)
            guard frame.width > 0 && frame.height > 0 else { return nil }
            for screen in NSScreen.screens {
                let visible = screen.visibleFrame
                // Accessibility uses the primary screen's top-left; AppKit uses its bottom-left.
                let area = CGRect(x: visible.minX, y: primary.frame.maxY - visible.maxY,
                    width: visible.width, height: visible.height)
                if area.contains(frame) {
                    return CGSize(width: area.width * screen.backingScaleFactor,
                        height: area.height * screen.backingScaleFactor)
                }
            }
            return nil
        }
    } catch {
        let environment = ProcessInfo.processInfo.environment
        if ["initial", "restored"].contains(phase),
            let root = environment["RUNNER_TEMP"], let source = environment["GITHUB_SHA"] {
            var record = snapshot
            record["schema_version"] = 1
            record["source_sha"] = source
            record["platform"] = "macOS"
            record["phase"] = phase
            record["coordinate_unit"] = "logical_points"
            if let bytes = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]),
                bytes.count <= 16384 {
                let path = URL(fileURLWithPath: root).appendingPathComponent("installed-native-window-geometry.json")
                try? bytes.write(to: path, options: [.withoutOverwriting])
            }
        }
        throw error
    }
}

func oversizedNormalState(_ path: URL, _ workArea: CGSize) throws {
    let properties = try path.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
    try check(properties.isRegularFile == true && properties.isSymbolicLink == false &&
        (properties.fileSize ?? 65537) <= 65536, "Owned native window state is not a bounded regular file")
    guard var saved = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as? [String: Any],
        var main = saved["main"] as? [String: Any], main["width"] is NSNumber,
        main["height"] is NSNumber, main["maximized"] is NSNumber
    else { throw ProbeFailure("Native window state did not retain its geometry") }
    // Simulate the saved normal size of a larger display; preserve every other preference.
    main["width"] = Int(workArea.width * 2)
    main["height"] = Int(workArea.height * 2)
    main["maximized"] = false
    saved["main"] = main
    try JSONSerialization.data(withJSONObject: saved, options: [.sortedKeys]).write(to: path)
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


struct PublicPlan {
    let raw: String
    let digest: String
    let document: [String: Any]
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

func pressNamed(_ process: Process, _ label: String, role: String? = nil, line: Int = #line) throws {
    var node = try visible(process, label, role: role, enabled: role != nil, line: line)
    for _ in 0..<4 {
        var actions: CFArray?
        if AXUIElementCopyActionNames(node, &actions) == .success,
            let names = actions as? [String], names.contains(kAXPressAction) {
            try press(node, line: line)
            return
        }
        guard let parent = attribute(node, kAXParentAttribute) else { break }
        try check(CFGetTypeID(parent) == AXUIElementGetTypeID(), "Unsupported accessibility parent")
        node = (parent as! AXUIElement)
    }
    throw ProbeFailure("Named UI control does not expose a press action", line: line)
}

func ownsKeyboard(_ process: Process) -> Bool {
    let system = AXUIElementCreateSystemWide()
    AXUIElementSetMessagingTimeout(system, 2)
    guard let focused = attribute(system, kAXFocusedApplicationAttribute),
        CFGetTypeID(focused) == AXUIElementGetTypeID()
    else { return false }
    var identifier: pid_t = 0
    return AXUIElementGetPid(focused as! AXUIElement, &identifier) == .success &&
        identifier == process.processIdentifier
}

func focus(_ process: Process, _ node: AXUIElement) throws {
    guard let running = NSRunningApplication(processIdentifier: process.processIdentifier) else {
        throw ProbeFailure("Owned running application is unavailable")
    }
    try check(running.activate(options: []), "Owned application activation was refused")
    try check(AXUIElementSetAttributeValue(application(process), kAXFrontmostAttribute as CFString, kCFBooleanTrue) == .success,
        "Owned application could not become frontmost")
    try check(AXUIElementSetAttributeValue(node, kAXFocusedAttribute as CFString, kCFBooleanTrue) == .success,
        "Owned UI control could not receive keyboard focus")
    var observation = "not observed"
    do {
        _ = try wait("owned keyboard focus") {
            try check(process.isRunning, "Installed Desktop exited before keyboard input")
            let frontmost = ownsKeyboard(process)
            let flag = attribute(node, kAXFocusedAttribute) as? Bool == true
            var same = false
            var role = "unavailable"
            if let focused = attribute(application(process), kAXFocusedUIElementAttribute),
                CFGetTypeID(focused) == AXUIElementGetTypeID() {
                let element = focused as! AXUIElement
                same = CFEqual(element, node)
                role = attribute(element, kAXRoleAttribute) as? String ?? "unknown"
            }
            observation = "frontmost=\(frontmost), target_flag=\(flag), target_matches=\(same), focused_role=\(role)"
            return frontmost && (flag || same) ? true : nil
        }
    } catch {
        throw ProbeFailure("\(error); native focus observation: \(observation)")
    }
}

func key(_ process: Process, _ code: CGKeyCode, flags: CGEventFlags = []) throws {
    try check(process.isRunning && ownsKeyboard(process),
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
        try check(process.isRunning && ownsKeyboard(process),
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

func readPublicPlan(_ process: Process, _ catalogs: Catalogs, _ locale: String,
    regionKey: String = "profiles.reviewNativeProfilePlan") throws -> PublicPlan {
    let region = try visible(process, catalogs.text(regionKey, locale))
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
                        if (object["change"] as? [String: Any])?["context"] is [String: Any] ||
                            (object["change"] as? [String: Any])?["snapshot"] is [String: Any] ||
                            (object["connection_id"] is String && object["origin"] is String && object["label"] is String) {
                            document = object
                            raw = value
                        }
                    }
                }
                return false
            }
            let roleSummary = roles.keys.sorted().map { "\($0)=\(roles[$0]!)" }.joined(separator: ",")
            observation = "nodes=\(nodes), strings=\(strings), JSON=\(jsonValues), plan=\(raw != nil), digest=\(digest != nil), roles=[\(roleSummary)]"
            guard let document = document, let raw = raw, let digest = digest else { return nil }
            return PublicPlan(raw: raw, digest: digest, document: document)
        }
    } catch {
        throw ProbeFailure("\(error); native review observation: \(observation)")
    }
}

func review(_ process: Process, _ catalogs: Catalogs, _ locale: String) throws -> Review {
    let publicPlan = try readPublicPlan(process, catalogs, locale)
    guard let change = publicPlan.document["change"] as? [String: Any],
        let context = change["context"] as? [String: Any], let action = change["action"] as? String
    else { throw ProbeFailure("Displayed profile review does not contain a context plan") }
    return Review(raw: publicPlan.raw, digest: publicPlan.digest, context: context, action: action)
}

func validate(_ review: Review, _ action: String, _ label: String, _ identifier: String? = nil) throws -> String {
    guard review.action == action, review.context["label"] as? String == label,
        let authority = review.context["authority"] as? [String: Any], authority["kind"] as? String == "local",
        let id = review.context["context_id"] as? String, !id.isEmpty, id.utf8.count <= 512
    else { throw ProbeFailure("Displayed context plan changed intent or authority") }
    if let expected = identifier { try check(id == expected, "Displayed context plan changed identity") }
    return id
}

func authorizeReviewed(_ process: Process, _ catalogs: Catalogs, _ checkKey: String, _ applyKey: String) throws {
    let confirmation = try visible(process, catalogs.text(checkKey), role: kAXCheckBoxRole, enabled: true)
    try check((attribute(confirmation, kAXValueAttribute) as? NSNumber)?.intValue == 0,
        "Native review was already confirmed")
    let apply = try visible(process, catalogs.text(applyKey), role: kAXButtonRole)
    try check(attribute(apply, kAXEnabledAttribute) as? Bool == false, "Unconfirmed native review was applicable")
    try press(confirmation)
    try press(visible(process, catalogs.text(applyKey), role: kAXButtonRole, enabled: true))
}

func confirm(_ process: Process, _ catalogs: Catalogs) throws {
    try authorizeReviewed(process, catalogs, "profiles.iReviewedThisExactPlanAndAuthorizeThisLocal",
        "profiles.applyReviewedChange")
    _ = try wait("context review completion") {
        try check(process.isRunning, "Installed Desktop exited during context apply")
        return match(application(process), label: try catalogs.text("profiles.reviewNativeProfilePlan"), role: nil, enabled: false) == nil ? true : nil
    }
}

func openPublicPlan(_ process: Process, _ catalogs: Catalogs,
    _ labelKey: String = "profiles.exactPublicPlan") throws {
    let disclosure = try visible(process, catalogs.text(labelKey), role: kAXDisclosureTriangleRole, enabled: true)
    func expanded() -> Bool? {
        if let value = attribute(disclosure, kAXExpandedAttribute) as? Bool { return value }
        if let value = attribute(disclosure, kAXValueAttribute) as? NSNumber,
            value.intValue == 0 || value.intValue == 1 { return value.intValue == 1 }
        return nil
    }
    if expanded() != true {
        try focus(process, disclosure)
        try key(process, 49)
    }
    _ = try wait("expanded public plan disclosure") {
        expanded() == true ? true : nil
    }
}

func context(_ process: Process, _ catalogs: Catalogs, _ label: String) throws -> Review {
    let field = try visible(process, catalogs.text("profiles.contextLabel"), role: kAXTextFieldRole, enabled: true)
    try enter(process, field, label)
    try pressNamed(process, catalogs.text("profiles.reviewContextCreation"), role: kAXButtonRole)
    try openPublicPlan(process, catalogs)
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
    try openPublicPlan(process, catalogs)
    _ = try validate(review(process, catalogs, "en"), "select", label, identifier)
    try confirm(process, catalogs)
    try selected(cli, identifier)
    _ = try visible(process, label + catalogs.text("profiles.selectedView"))
}

func preferenceReady(_ process: Process, _ catalogs: Catalogs, _ locale: String) throws -> AXUIElement {
    let label = try catalogs.text("language.label", locale)
    let selector = try visible(process, label, role: kAXPopUpButtonRole, enabled: true)
    let group = try visible(process, label, role: kAXGroupRole)
    _ = try wait("acknowledged native appearance preferences") {
        match(group, label: try catalogs.text("status.applying", locale), role: nil, enabled: false) == nil ? true : nil
    }
    return selector
}

func language(_ process: Process, _ catalogs: Catalogs, _ previous: String, _ next: String) throws {
    let selector = try preferenceReady(process, catalogs, previous)
    let expected = try catalogs.name(next)
    if attribute(selector, kAXValueAttribute) as? String != expected {
        try press(selector)
        let option = try wait("packaged native language option") {
            match(application(process), label: try catalogs.name(next), role: kAXMenuItemRole, enabled: true)
        }
        try press(option)
    }
    _ = try preferenceReady(process, catalogs, next)
}

func theme(_ process: Process, _ catalogs: Catalogs, _ locale: String, _ dark: Bool) throws {
    let desiredLabel = try catalogs.text(dark ? "shell.light" : "shell.dark", locale)
    if match(application(process), label: desiredLabel, role: kAXButtonRole, enabled: true) == nil {
        try pressNamed(process, catalogs.text(dark ? "shell.dark" : "shell.light", locale), role: kAXButtonRole)
    }
    _ = try visible(process, desiredLabel, role: kAXButtonRole, enabled: true)
    _ = try preferenceReady(process, catalogs, locale)
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


func corporateStage(_ name: String) {
    FileHandle.standardOutput.write(Data(("AI_STP_NATIVE_DESKTOP_STAGE_V1 " + name + "\n").utf8))
}

struct CorporateFixture {
    let nonce: String
    let source: String
    let origin: String
    let account: String
    let organization: String
    let project: String
    let checkout: URL
    let git: String
    let result: URL

    init(_ path: String, _ environment: [String: String]) throws {
        let url = URL(fileURLWithPath: path).standardizedFileURL
        guard let temporary = environment["RUNNER_TEMP"], let source = environment["GITHUB_SHA"] else {
            throw ProbeFailure("Native corporate runner ownership is unavailable")
        }
        let root = URL(fileURLWithPath: temporary).standardizedFileURL.path + "/"
        let properties = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        try check(url.path.hasPrefix(root) && properties.isRegularFile == true &&
            properties.isSymbolicLink == false && (properties.fileSize ?? 16385) <= 16384,
            "Native corporate fixture file is not owned and bounded")
        guard let value = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: String],
            value.count == 10, value["protocol"] == "ai-stp-native-desktop-fixture/1",
            value["source_sha"] == source, let nonce = value["nonce"],
            nonce.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil,
            let origin = value["origin"],
            origin.range(of: "^http://127[.]0[.]0[.]1:[1-9][0-9]{0,4}$", options: .regularExpression) != nil,
            let account = value["account_id"], !account.isEmpty, account.utf8.count <= 128,
            let organization = value["organization_id"], !organization.isEmpty, organization.utf8.count <= 128,
            let project = value["project_id"], !project.isEmpty, project.utf8.count <= 128,
            let result = value["result_path"],
            result == url.deletingLastPathComponent().appendingPathComponent("native-corporate-journey.json").path,
            let checkout = value["checkout_root"],
            checkout == url.deletingLastPathComponent().appendingPathComponent("checkout").path,
            let git = value["git_executable"], git.hasPrefix("/"),
            FileManager.default.fileExists(atPath: git)
        else { throw ProbeFailure("Native corporate fixture contract differs") }
        try check(!FileManager.default.fileExists(atPath: result), "Native corporate result already exists")
        self.nonce = nonce
        self.source = source
        self.origin = origin
        self.account = account
        self.organization = organization
        self.project = project
        self.checkout = URL(fileURLWithPath: checkout)
        self.git = git
        self.result = URL(fileURLWithPath: result)
    }
}

func profileOption(_ process: Process, _ catalogs: Catalogs, _ key: String, _ name: String, line: Int = #line) throws {
    let selector = try visible(process, catalogs.text(key), role: kAXPopUpButtonRole, enabled: true, line: line)
    if attribute(selector, kAXValueAttribute) as? String != name {
        try press(selector, line: line)
        let option = try wait("owned native profile option", line: line) {
            match(application(process), label: name, role: kAXMenuItemRole, enabled: true)
        }
        try press(option, line: line)
    }
    _ = try wait("selected native profile option", line: line) {
        attribute(selector, kAXValueAttribute) as? String == name ? true : nil
    }
}

func remoteReview(_ review: Review, _ fixture: CorporateFixture, _ action: String,
    _ connection: String, _ identifier: String? = nil) throws -> String {
    guard review.action == action, review.context["label"] as? String == "Native corporate context",
        let authority = review.context["authority"] as? [String: Any], authority["kind"] as? String == "remote",
        let organization = authority["organization"] as? [String: Any],
        organization["organization_id"] as? String == fixture.organization,
        let account = authority["account"] as? [String: Any], account["account_id"] as? String == fixture.account,
        account["origin"] as? String == fixture.origin,
        let enrollment = account["connection"] as? [String: Any], enrollment["connection_id"] as? String == connection,
        let id = review.context["context_id"] as? String, !id.isEmpty, id.utf8.count <= 512
    else { throw ProbeFailure("Displayed corporate plan changed intent or authority") }
    if let expected = identifier { try check(id == expected, "Displayed corporate plan changed context identity") }
    return id
}

func corporateApproval(_ fixture: CorporateFixture, _ code: String) throws {
    try check(!code.isEmpty && code.utf8.count <= 128, "Native approval code is invalid")
    let request: [String: Any] = [
        "protocol": "ai-stp-native-desktop-fixture/1", "nonce": fixture.nonce,
        "sequence": 1, "action": "approve_device", "user_code": code,
    ]
    let bytes = try JSONSerialization.data(withJSONObject: request, options: [.sortedKeys])
    FileHandle.standardOutput.write(Data("AI_STP_NATIVE_DESKTOP_FIXTURE_V1 ".utf8) + bytes + Data([10]))
    guard let line = readLine(), line.utf8.count <= 4096, let data = line.data(using: .utf8),
        let reply = try JSONSerialization.jsonObject(with: data) as? [String: Any],
        reply.count == 4, reply["protocol"] as? String == "ai-stp-native-desktop-fixture/1",
        reply["nonce"] as? String == fixture.nonce, reply["sequence"] as? Int == 1,
        reply["approved"] as? Bool == true
    else { throw ProbeFailure("Native approval response differs") }
}

func corporateSession(_ cli: URL, _ fixture: CorporateFixture, _ connection: String) throws {
    let status = try native(cli, ["account", "status", "--connection", connection])
    guard status["origin"] as? String == fixture.origin, let session = status["session"] as? [String: Any],
        session["state"] as? String == "authorized", session["account_id"] as? String == fixture.account
    else { throw ProbeFailure("Original corporate account session changed") }
}

func corporate(_ process: Process, _ cli: URL, _ catalogs: Catalogs, _ fixture: CorporateFixture,
    _ identity: Data) throws -> (String, String, String) {
    try pressNamed(process, catalogs.text("shell.connections"), role: "AXLink")
    try enter(process, visible(process, catalogs.text("profiles.connectionLabel"), role: kAXTextFieldRole, enabled: true),
        "Native company connection")
    try enter(process, visible(process, catalogs.text("profiles.serverOrigin"), role: kAXTextFieldRole, enabled: true), fixture.origin)
    try pressNamed(process, catalogs.text("profiles.checkServerSignInMethods"), role: kAXButtonRole)
    try profileOption(process, catalogs, "profiles.signInMethod", "github")
    try pressNamed(process, catalogs.text("profiles.reviewConnectionCreation"), role: kAXButtonRole)
    try openPublicPlan(process, catalogs)
    corporateStage("connection")
    let plan = try readPublicPlan(process, catalogs, "en").document
    guard plan["label"] as? String == "Native company connection", plan["origin"] as? String == fixture.origin,
        plan["provider"] as? String == "github", let connection = plan["connection_id"] as? String, !connection.isEmpty
    else { throw ProbeFailure("Displayed connection plan changed intent") }
    corporateStage("connection_reviewed")
    try confirm(process, catalogs)
    let connections = try native(cli, ["account", "connections", "list"])["connections"] as? [[String: Any]] ?? []
    let stored = connections.filter { $0["connection_id"] as? String == connection }
    try check(stored.count == 1 && stored[0]["state"] as? String == "ready" &&
        stored[0]["label"] as? String == "Native company connection" &&
        stored[0]["origin"] as? String == fixture.origin && stored[0]["provider"] as? String == "github",
        "Stored connection changed the reviewed intent")
    corporateStage("connection_saved")
    try pressNamed(process, catalogs.text("profiles.openThisAccountSession"), role: "AXLink")
    let provider = try visible(process, "GitHub", role: kAXCheckBoxRole, enabled: true)
    try check(attribute(provider, kAXSubroleAttribute) as? String == "AXToggle",
        "Native sign-in provider does not expose its toggle role")
    let state = (attribute(provider, kAXValueAttribute) as? NSNumber)?.intValue
    try check(state == 0 || state == 1, "Native sign-in provider has an invalid toggle state")
    if state == 0 { try press(provider) }
    _ = try wait("selected native sign-in provider") {
        (attribute(provider, kAXValueAttribute) as? NSNumber)?.intValue == 1 ? true : nil
    }
    try pressNamed(process, catalogs.text("auth.startSignIn"), role: kAXButtonRole)
    _ = try visible(process, catalogs.text("auth.approveThisDeviceInYourBrowser"))
    corporateStage("pending")
    let pending = try native(cli, ["account", "status", "--connection", connection])["session"] as? [String: Any]
    guard pending?["state"] as? String == "pending", let code = pending?["user_code"] as? String else {
        throw ProbeFailure("Native sign-in did not retain a pending confirmation")
    }
    try pressNamed(process, catalogs.text("shell.connections"), role: "AXLink")
    try pressNamed(process, catalogs.text("profiles.openThisAccountSession"), role: "AXLink")
    _ = try visible(process, catalogs.text("auth.approveThisDeviceInYourBrowser"))
    let again = try native(cli, ["account", "status", "--connection", connection])["session"] as? [String: Any]
    try check(again?["state"] as? String == "pending" && again?["user_code"] as? String == code,
        "Navigation replaced the original pending confirmation")
    _ = try wait("original pending confirmation displayed") {
        match(application(process), label: code, role: nil, enabled: false) == nil ? nil : true
    }
    corporateStage("approval")
    try corporateApproval(fixture, code)
    try pressNamed(process, catalogs.text("auth.openBrowserAndConfirm"), role: kAXButtonRole)
    _ = try visible(process, catalogs.text("auth.signedIn"))
    try corporateSession(cli, fixture, connection)
    try pressNamed(process, catalogs.text("shell.connections"), role: "AXLink")
    try enter(process, visible(process, catalogs.text("profiles.contextLabel"), role: kAXTextFieldRole, enabled: true),
        "Native corporate context")
    corporateStage("context_connection")
    try profileOption(process, catalogs, "profiles.contextConnection", "Native company connection · " + fixture.origin)
    corporateStage("organization")
    try pressNamed(process, catalogs.text("profiles.readAvailableOrganizations"), role: kAXButtonRole)
    try profileOption(process, catalogs, "profiles.organization", "Installed fixture company · corporate")
    try pressNamed(process, catalogs.text("profiles.reviewContextCreation"), role: kAXButtonRole)
    try openPublicPlan(process, catalogs)
    corporateStage("context")
    let retained = try review(process, catalogs, "en")
    let context = try remoteReview(retained, fixture, "create", connection)
    try confirm(process, catalogs)
    let listed = try savedContexts(cli)["contexts"] as? [[String: Any]] ?? []
    let local = listed.filter { (($0["context"] as? [String: Any])?["authority"] as? [String: Any])?["kind"] as? String == "local" }
    try check(listed.count == 3 && local.count == 2, "Personal and corporate contexts did not coexist")
    let card = try visible(process, "Native corporate context", role: kAXGroupRole)
    let selection = try wait("owned corporate context selection") {
        match(card, label: try catalogs.text("profiles.reviewViewSelection"), role: kAXButtonRole, enabled: true)
    }
    corporateStage("selection")
    try press(selection)
    try openPublicPlan(process, catalogs)
    _ = try remoteReview(review(process, catalogs, "en"), fixture, "select", connection, context)
    try confirm(process, catalogs)
    try selected(cli, context)
    guard let authority = retained.context["authority"] as? [String: Any],
        let account = authority["account"] as? [String: Any],
        let device = account["device_id"] as? String, !device.isEmpty else {
        throw ProbeFailure("Corporate context did not resolve its enrolled device")
    }
    let observed = try JSONSerialization.data(withJSONObject: native(cli, ["device", "show"]), options: [.sortedKeys])
    try check(observed == identity, "Corporate sign-in replaced the original native identity")
    return (context, connection, device)
}


struct PendingCheckout {
    let request: String
    let confirmation: String
    let confirmationDigest: String
    let context: String
    let localProject: String
}

func checkoutIntent(_ publicPlan: PublicPlan, _ fixture: CorporateFixture, _ context: String,
    _ connection: String, _ device: String, _ action: String, _ request: String? = nil) throws -> (String, String) {
    let plan = publicPlan.document
    guard let operation = plan["operation_id"] as? String, !operation.isEmpty, operation.utf8.count <= 128,
        let change = plan["change"] as? [String: Any], change["action"] as? String == action,
        let snapshot = change["snapshot"] as? [String: Any],
        (snapshot["context"] as? [String: Any])?["context_id"] as? String == context,
        let account = snapshot["account"] as? [String: Any],
        account["origin"] as? String == fixture.origin, account["account_id"] as? String == fixture.account,
        account["device_id"] as? String == device,
        (account["connection"] as? [String: Any])?["connection_id"] as? String == connection,
        (snapshot["organization"] as? [String: Any])?["organization_id"] as? String == fixture.organization,
        (snapshot["target"] as? [String: Any])?["remote_project_id"] as? String == fixture.project,
        let local = snapshot["local_project"] as? [String: Any],
        let localID = local["local_project_id"] as? String, !localID.isEmpty,
        let root = local["root"] as? [String: Any], (root["identity"] as? [String])?.count == 2
    else { throw ProbeFailure("Displayed checkout plan changed its original authority") }
    for value in [plan["checkout_root"], root["path"]] {
        guard let path = value as? [String: Any], let encoded = path["utf8_base64"] as? String,
            encoded.utf8.count <= 43692, Data(base64Encoded: encoded) == Data(fixture.checkout.path.utf8),
            path["display"] as? String == fixture.checkout.path.precomposedStringWithCanonicalMapping
        else { throw ProbeFailure("Displayed checkout plan changed its physical path") }
    }
    if let expected = request {
        try check(change["request_operation_id"] as? String == expected,
            "Displayed checkout plan replaced the original request")
    }
    return (operation, localID)
}

func beginCorporateCheckout(_ process: Process, _ cli: URL, _ catalogs: Catalogs,
    _ fixture: CorporateFixture, _ context: String, _ connection: String, _ device: String) throws -> PendingCheckout {
    corporateStage("checkout_preview")
    // Fixture preparation uses the installed public engine, never application IPC.
    let prepared = try native(cli, ["project", "passport", "plan", "--root", fixture.checkout.path])
    guard let passport = prepared["plan"] as? [String: Any], let digest = prepared["plan_digest"] as? String,
        digest.range(of: "^sha256:[0-9a-f]{64}$", options: .regularExpression) != nil,
        let local = ((passport["operation"] as? [String: Any])?["passport"] as? [String: Any])?["stable_id"] as? String
    else { throw ProbeFailure("Owned checkout passport preparation differs") }
    let preparation = fixture.checkout.deletingLastPathComponent().appendingPathComponent("checkout-passport.json")
    try JSONSerialization.data(withJSONObject: passport, options: [.sortedKeys]).write(to: preparation, options: [.withoutOverwriting])
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: preparation.path)
    _ = try native(cli, ["local", "apply", "--plan", preparation.path, "--plan-digest", digest])
    try pressNamed(process, catalogs.text("shell.company"), role: "AXLink")
    try pressNamed(process, "Read projects",
        role: kAXButtonRole)
    _ = try visible(process, "Installed shared project")
    try pressNamed(process, catalogs.text("corporate.reviewLocalCheckout"), role: kAXButtonRole)
    try enter(process, visible(process, catalogs.text("checkoutPreview.checkoutDirectory"), role: kAXTextFieldRole, enabled: true),
        fixture.checkout.path)
    try enter(process, visible(process, catalogs.text("checkoutPreview.gitExecutableOptional"), role: kAXTextFieldRole, enabled: true),
        fixture.git)
    try pressNamed(process, catalogs.text("checkoutPreview.previewCheckout"), role: kAXButtonRole)
    _ = try visible(process, catalogs.text("checkoutPreview.checkoutVerifiedForReview"))
    corporateStage("checkout_request")
    try pressNamed(process, catalogs.text("checkoutPreview.reviewLinkRequest"), role: kAXButtonRole)
    try openPublicPlan(process, catalogs, "checkoutPreview.exactCheckoutPlan")
    let requestPlan = try readPublicPlan(process, catalogs, "en", regionKey: "checkoutPreview.reviewCorporateCheckoutChange")
    let (request, requestLocal) = try checkoutIntent(requestPlan, fixture, context, connection, device, "request")
    try check(requestLocal == local, "Checkout review changed its registered local project")
    try authorizeReviewed(process, catalogs, "checkoutPreview.iReviewedThisExactCheckoutPlanAndAuthorizeIts",
        "checkoutPreview.applyReviewedCheckoutChange")
    corporateStage("checkout_confirmation")
    try pressNamed(process, catalogs.text("checkoutPreview.reviewLinkConfirmation"), role: kAXButtonRole)
    try openPublicPlan(process, catalogs, "checkoutPreview.exactCheckoutPlan")
    let confirmationPlan = try readPublicPlan(process, catalogs, "en", regionKey: "checkoutPreview.reviewCorporateCheckoutChange")
    let (confirmation, confirmationLocal) = try checkoutIntent(confirmationPlan, fixture, context, connection, device, "confirm", request)
    try check(confirmationLocal == local && confirmation != request, "Checkout confirmation changed its original operation")
    try authorizeReviewed(process, catalogs, "checkoutPreview.iReviewedThisExactCheckoutPlanAndAuthorizeIts",
        "checkoutPreview.applyReviewedCheckoutChange")
    _ = try visible(process, catalogs.text("error.requestFailed"))
    let unconfirmed = try native(cli, ["corporate", "project", "link", "show", "--operation", confirmation])
    try check(unconfirmed["state"] as? String == "applying" &&
        unconfirmed["plan_digest"] as? String == confirmationPlan.digest,
        "Lost checkout reply did not retain the original pending confirmation")
    return PendingCheckout(request: request, confirmation: confirmation, confirmationDigest: confirmationPlan.digest,
        context: context, localProject: local)
}

func resumeCorporateCheckout(_ process: Process, _ cli: URL, _ catalogs: Catalogs,
    _ fixture: CorporateFixture, _ pending: PendingCheckout, _ connection: String, _ device: String) throws -> [String: String] {
    corporateStage("checkout_reconciliation")
    try pressNamed(process, catalogs.text("shell.activity"), role: "AXLink")
    try pressNamed(process, catalogs.text("checkoutOperations.readCheckoutHistory"), role: kAXButtonRole)
    try pressNamed(process, catalogs.text("checkoutOperations.inspect") + " " + pending.confirmation, role: kAXButtonRole)
    try authorizeReviewed(process, catalogs, "checkoutOperations.iReviewedThisOriginalIntentAndAuthorizeOutcomeReconciliation",
        "checkoutOperations.reconcileOriginalOutcome")
    _ = try visible(process, catalogs.text("checkoutOperations.reviewOriginalLocalBinding"), role: kAXButtonRole, enabled: true)
    let reconciled = try native(cli, ["corporate", "project", "link", "show", "--operation", pending.confirmation])
    try check(reconciled["state"] as? String == "completed" &&
        reconciled["operation_id"] as? String == pending.confirmation &&
        reconciled["plan_digest"] as? String == pending.confirmationDigest,
        "Checkout reconciliation replaced the original confirmation")
    let root = try visible(process, catalogs.text("checkoutOperations.registeredCheckoutForBinding"),
        role: kAXTextFieldRole, enabled: true)
    try check(attribute(root, kAXValueAttribute) as? String == fixture.checkout.path,
        "Checkout recovery did not retain the original directory")
    try enter(process, visible(process, catalogs.text("checkoutOperations.trustedGitExecutableForCheckoutReviewOptional"),
        role: kAXTextFieldRole, enabled: true), fixture.git)
    corporateStage("checkout_binding")
    try pressNamed(process, catalogs.text("checkoutOperations.reviewOriginalLocalBinding"), role: kAXButtonRole)
    try openPublicPlan(process, catalogs, "checkoutOperations.exactRetainedCheckoutNextPlan")
    let plan = try readPublicPlan(process, catalogs, "en", regionKey: "checkoutOperations.reviewRetainedCheckoutNextChange")
    let (adoption, local) = try checkoutIntent(plan, fixture, pending.context, connection, device, "adopt", pending.request)
    try check(local == pending.localProject && adoption != pending.request && adoption != pending.confirmation,
        "Checkout adoption replaced the original project or operation")
    try authorizeReviewed(process, catalogs, "checkoutOperations.iReviewedThisExactRetainedCheckoutChangeAndAuthorize",
        "checkoutOperations.applyReviewedOriginalCheckoutChange")
    _ = try visible(process, catalogs.text("checkoutOperations.originalCorporateProjectBindingReceiptSaved"))
    let retained = try native(cli, ["corporate", "project", "link", "show", "--operation", adoption])
    guard retained["state"] as? String == "completed", retained["plan_digest"] as? String == plan.digest,
        let effect = retained["effect"] as? [String: Any], let link = effect["link"] as? [String: Any],
        link["state"] as? String == "linked", let linkID = link["link_id"] as? String, !linkID.isEmpty
    else { throw ProbeFailure("Installed checkout binding does not match its original receipt") }
    return [
        "request_operation_id": pending.request, "confirmation_operation_id": pending.confirmation,
        "adoption_operation_id": adoption, "context_id": pending.context,
        "local_project_id": local, "link_id": linkID,
    ]
}

func prove() throws {
    let environment = ProcessInfo.processInfo.environment
    try check(environment["GITHUB_ACTIONS"] == "true" && environment["RUNNER_ENVIRONMENT"] == "github-hosted" && environment["RUNNER_OS"] == "macOS",
        "A disposable hosted macOS runner is required")
    try check(AXIsProcessTrusted(), "Hosted macOS accessibility client lacks authorization")
    try check(CGPreflightPostEventAccess(), "Hosted macOS keyboard client lacks authorization")
    let arguments = CommandLine.arguments
    try check(arguments.count == 5, "Installed executable, CLI, message catalog and result paths are required")
    let corporateFixture = try environment["AI_STP_NATIVE_DESKTOP_FIXTURE"].map { try CorporateFixture($0, environment) }
    corporateStage("owner")
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

    let package = app.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    guard let identifier = Bundle(url: package)?.bundleIdentifier,
        let configuration = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    else { throw ProbeFailure("Native application configuration identity is unavailable") }
    let windowState = configuration.appendingPathComponent(identifier).appendingPathComponent(".window-state.json")
    try check(!FileManager.default.fileExists(atPath: windowState.path), "First-run native window state is required")
    corporateStage("installed")
    var process = try launch(app)
    defer { if process.isRunning { process.terminate() } }
    let initialWorkArea = try normalWorkArea(process)
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
    corporateStage("personal")
    let (selectedID, dark, combinations) = try personal(process, cli, catalogs)
    try check(combinations == catalogs.languages.count * 2, "Native appearance cases are incomplete")
    try close(process)
    fputs("Restarting the initialized workspace\n", stderr)
    try oversizedNormalState(windowState, initialWorkArea)
    process = try launch(app)
    _ = try normalWorkArea(process, phase: "restored")
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
    if let fixture = corporateFixture {
        let (context, connection, device) = try corporate(process, cli, catalogs, fixture, identity)
        try close(process)
        corporateStage("restart")
        process = try launch(app)
        _ = try visible(process, catalogs.text("language.label"), role: kAXPopUpButtonRole, enabled: true)
        try selected(cli, context)
        try pressNamed(process, catalogs.text("shell.connections"), role: "AXLink")
        _ = try visible(process, "Native corporate context" + catalogs.text("profiles.selectedView"))
        try check((try savedContexts(cli)["contexts"] as? [[String: Any]])?.count == 3,
            "Restart lost coexisting personal and corporate contexts")
        try corporateSession(cli, fixture, connection)
        let observed = try JSONSerialization.data(withJSONObject: native(cli, ["device", "show"]), options: [.sortedKeys])
        try check(observed == identity, "Corporate restart changed the original device identity")
        let pendingCheckout = try beginCorporateCheckout(process, cli, catalogs, fixture, context, connection, device)
        try close(process)
        corporateStage("checkout_restart")
        process = try launch(app)
        _ = try visible(process, catalogs.text("language.label"), role: kAXPopUpButtonRole, enabled: true)
        try selected(cli, context)
        let checkout = try resumeCorporateCheckout(process, cli, catalogs, fixture, pendingCheckout, connection, device)
        try corporateSession(cli, fixture, connection)
        let afterCheckout = try JSONSerialization.data(withJSONObject: native(cli, ["device", "show"]), options: [.sortedKeys])
        try check(afterCheckout == identity, "Checkout recovery changed the original enrolled identity")
        try close(process)
        let keys = [
            "installed_personal_journey_retained", "connection_exact_plan_and_confirmation",
            "original_pending_confirmation_after_navigation", "device_bound_account_session",
            "corporate_context_exact_plan_and_confirmation", "personal_and_corporate_contexts_coexist",
            "context_view_selection_explicit", "corporate_context_survives_restart",
            "original_device_survives_restart", "original_account_and_origin_preserved",
        ]
        let retained: [String: Any] = [
            "schema_version": 2, "source_sha": fixture.source,
            "controls": Dictionary(uniqueKeysWithValues: keys.map { ($0, true) }),
            "checkout_controls": Dictionary(uniqueKeysWithValues: [
                "committed_checkout_preview", "request_exact_plan_and_confirmation",
                "confirmation_exact_plan_and_confirmation", "committed_reply_lost",
                "original_operation_reconciled_after_restart", "binding_exact_plan_and_confirmation",
                "original_link_and_device_preserved", "unowned_checkout_bytes_and_identity_preserved",
            ].map { ($0, true) }),
            "checkout": checkout,
            "enrolled_device_id": device, "desktop_process_stopped": !process.isRunning,
        ]
        try JSONSerialization.data(withJSONObject: retained, options: [.sortedKeys]).write(to: fixture.result, options: [.withoutOverwriting])
    } else {
        try close(process)
    }
    corporateStage("complete")
    let result: [String: Any] = [
        "cli_version": cliVersion,
        "theme_locale_observations": combinations,
        "normal_window_controls": [
            "first_normal_window_within_work_area": true,
            "oversized_normal_state_restored_within_work_area": true,
            "context_and_preferences_survive_geometry_recovery": true,
        ],
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
    try output.write(to: URL(fileURLWithPath: arguments[4]), options: [.withoutOverwriting])
}

do {
    try prove()
} catch {
    let line = (error as? ProbeFailure)?.sourceLine ?? 0
    FileHandle.standardOutput.write(Data(("AI_STP_NATIVE_DESKTOP_FAILURE_V1 " + String(line) + "\n").utf8))
    fputs("\(error)\n", stderr)
    exit(1)
}

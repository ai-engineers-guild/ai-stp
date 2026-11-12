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


struct ProfilePlan {
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

func profilePlan(_ process: Process, _ catalogs: Catalogs, _ locale: String) throws -> ProfilePlan {
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
                        if (object["change"] as? [String: Any])?["context"] is [String: Any] ||
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
            return ProfilePlan(raw: raw, digest: digest, document: document)
        }
    } catch {
        throw ProbeFailure("\(error); native review observation: \(observation)")
    }
}

func review(_ process: Process, _ catalogs: Catalogs, _ locale: String) throws -> Review {
    let publicPlan = try profilePlan(process, catalogs, locale)
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

func openPublicPlan(_ process: Process, _ catalogs: Catalogs) throws {
    let disclosure = try visible(process, catalogs.text("profiles.exactPublicPlan"), role: kAXDisclosureTriangleRole, enabled: true)
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


func corporateStage(_ name: String) {
    FileHandle.standardOutput.write(Data(("AI_STP_NATIVE_DESKTOP_STAGE_V1 " + name + "\n").utf8))
}

struct CorporateFixture {
    let nonce: String
    let source: String
    let origin: String
    let account: String
    let organization: String
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
            value.count == 8, value["protocol"] == "ai-stp-native-desktop-fixture/1",
            value["source_sha"] == source, let nonce = value["nonce"],
            nonce.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil,
            let origin = value["origin"],
            origin.range(of: "^http://127[.]0[.]0[.]1:[1-9][0-9]{0,4}$", options: .regularExpression) != nil,
            let account = value["account_id"], !account.isEmpty, account.utf8.count <= 128,
            let organization = value["organization_id"], !organization.isEmpty, organization.utf8.count <= 128,
            let project = value["project_id"], !project.isEmpty, project.utf8.count <= 128,
            let result = value["result_path"],
            result == url.deletingLastPathComponent().appendingPathComponent("native-corporate-journey.json").path
        else { throw ProbeFailure("Native corporate fixture contract differs") }
        try check(!FileManager.default.fileExists(atPath: result), "Native corporate result already exists")
        self.nonce = nonce
        self.source = source
        self.origin = origin
        self.account = account
        self.organization = organization
        self.result = URL(fileURLWithPath: result)
    }
}

func profileOption(_ process: Process, _ catalogs: Catalogs, _ key: String, _ name: String) throws {
    let selector = try visible(process, catalogs.text(key), role: kAXPopUpButtonRole, enabled: true)
    if attribute(selector, kAXValueAttribute) as? String != name {
        try press(selector)
        let option = try wait("owned native profile option") {
            match(application(process), label: name, role: kAXMenuItemRole, enabled: true)
        }
        try press(option)
    }
    _ = try wait("selected native profile option") {
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
    let plan = try profilePlan(process, catalogs, "en").document
    guard plan["label"] as? String == "Native company connection", plan["origin"] as? String == fixture.origin,
        plan["provider"] as? String == "github", let connection = plan["connection_id"] as? String, !connection.isEmpty
    else { throw ProbeFailure("Displayed connection plan changed intent") }
    corporateStage("connection_reviewed")
    try confirm(process, catalogs)
    corporateStage("connection_saved")
    try pressNamed(process, catalogs.text("profiles.openThisAccountSession"), role: "AXLink")
    try pressNamed(process, "GitHub", role: kAXButtonRole)
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
    try profileOption(process, catalogs, "profiles.contextConnection", "Native company connection · " + fixture.origin)
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
    var ancestor: AXUIElement? = try visible(process, "Native corporate context")
    var button: AXUIElement?
    for _ in 0..<6 {
        guard let node = ancestor else { break }
        button = match(node, label: try catalogs.text("profiles.reviewViewSelection"), role: kAXButtonRole, enabled: true)
        if button != nil { break }
        if let parent = attribute(node, kAXParentAttribute), CFGetTypeID(parent) == AXUIElementGetTypeID() {
            ancestor = (parent as! AXUIElement)
        } else { ancestor = nil }
    }
    guard let selection = button else { throw ProbeFailure("Owned corporate context selection was not found") }
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

    corporateStage("installed")
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
    corporateStage("personal")
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
        try close(process)
        let keys = [
            "installed_personal_journey_retained", "connection_exact_plan_and_confirmation",
            "original_pending_confirmation_after_navigation", "device_bound_account_session",
            "corporate_context_exact_plan_and_confirmation", "personal_and_corporate_contexts_coexist",
            "context_view_selection_explicit", "corporate_context_survives_restart",
            "original_device_survives_restart", "original_account_and_origin_preserved",
        ]
        let retained: [String: Any] = [
            "schema_version": 1, "source_sha": fixture.source,
            "controls": Dictionary(uniqueKeysWithValues: keys.map { ($0, true) }),
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

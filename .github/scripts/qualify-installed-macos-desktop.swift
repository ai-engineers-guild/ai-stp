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
    var nodes = [root]
    for _ in 0..<2500 {
        guard let node = nodes.popLast() else { break }
        if role == nil || attribute(node, kAXRoleAttribute) as? String == role {
            for name in [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute] {
                if attribute(node, name) as? String == label,
                    !enabled || attribute(node, kAXEnabledAttribute) as? Bool == true {
                    return node
                }
            }
        }
        if let children = attribute(node, kAXChildrenAttribute) as? [AXUIElement] {
            nodes.append(contentsOf: children.reversed())
        }
    }
    return nil
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

func prove() throws {
    try check(AXIsProcessTrusted(), "Hosted macOS accessibility client lacks authorization")
    let arguments = CommandLine.arguments
    try check(arguments.count == 3, "Installed executable and CLI paths are required")
    let app = URL(fileURLWithPath: arguments[1])
    let cli = URL(fileURLWithPath: arguments[2])
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
    try press(visible(process,
        "Initialize or resume this device using the selected credential storage.", role: kAXCheckBoxRole))
    try press(visible(process, "Initialize workspace", role: kAXButtonRole, enabled: true))
    fputs("Invoked enabled workspace initialization\
", stderr)
    do {
        _ = try visible(process, "Initialized")
    } catch {
        if let report = try? native(cli, ["doctor"]), let checks = report["checks"] as? [[String: Any]] {
            let ready = checks.contains {
                $0["name"] as? String == "local_identity" && $0["state"] as? String == "ready"
            }
            fputs("Independent local identity ready: \\(ready)\
", stderr)
        }
        throw error
    }
    let identity = try JSONSerialization.data(withJSONObject: native(cli, ["device", "show"]), options: [.sortedKeys])
    try close(process)
    fputs("Restarting the initialized workspace\
", stderr)
    process = try launch(app)
    _ = try visible(process, "Engine \(cliVersion)")
    try settings(process)
    _ = try visible(process, "Initialized")
    let restarted = try JSONSerialization.data(withJSONObject: native(cli, ["device", "show"]), options: [.sortedKeys])
    try check(identity == restarted, "Installed device identity changed after restart")
    try close(process)
    print(cliVersion)
}

do {
    try prove()
} catch {
    fputs("\(error)\n", stderr)
    exit(1)
}

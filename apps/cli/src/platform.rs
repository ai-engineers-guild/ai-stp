//! Canonical public execution-platform names, distinct from Rust target triples.

pub(crate) fn current() -> Option<&'static str> {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("linux", "x86_64") => Some("linux/x86_64"),
        ("linux", "aarch64") => Some("linux/arm64"),
        ("macos", "x86_64") => Some("macos/x86_64"),
        ("macos", "aarch64") => Some("macos/arm64"),
        ("windows", "x86_64") => Some("windows/x86_64"),
        ("windows", "aarch64") => Some("windows/arm64"),
        _ => None,
    }
}

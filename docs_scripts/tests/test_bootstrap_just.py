"""The pinned `just` bootstrapper: every platform it claims, it can serve."""

import platform
import unittest

from docs_scripts import bootstrap_just


class BootstrapJustTests(unittest.TestCase):
    def test_every_declared_platform_has_a_checksum(self) -> None:
        # A table that names an asset it cannot verify is worse than one that
        # does not name it: the download would proceed unchecked.
        for key, asset in bootstrap_just.ASSET_FOR.items():
            self.assertIn(asset, bootstrap_just.SHA256, key)

    def test_every_checksum_belongs_to_a_declared_platform(self) -> None:
        declared = set(bootstrap_just.ASSET_FOR.values())
        for asset in bootstrap_just.SHA256:
            self.assertIn(asset, declared, asset)

    def test_the_names_python_actually_reports_all_resolve(self) -> None:
        # One machine is called different things depending on who asks: `arm64`
        # on macOS, `aarch64` on Linux, `amd64` on some Linux builds. CI failed
        # on exactly this — `Darwin arm64` was unsupported.
        expected = {
            ("Linux", "x86_64"): "x86_64-unknown-linux-musl",
            ("Linux", "amd64"): "x86_64-unknown-linux-musl",
            ("Linux", "aarch64"): "aarch64-unknown-linux-musl",
            ("Linux", "arm64"): "aarch64-unknown-linux-musl",
            ("Darwin", "arm64"): "aarch64-apple-darwin",
            ("Darwin", "aarch64"): "aarch64-apple-darwin",
            ("Darwin", "x86_64"): "x86_64-apple-darwin",
            ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
            ("Windows", "x86_64"): "x86_64-pc-windows-msvc",
            ("Windows", "ARM64"): "aarch64-pc-windows-msvc",
            ("Windows", "aarch64"): "aarch64-pc-windows-msvc",
        }
        for (system, machine), fragment in expected.items():
            with self.subTest(system=system, machine=machine):
                self.assertIn(fragment, self._asset(system, machine))

    def test_an_unsupported_platform_is_refused_by_name(self) -> None:
        # Guessing an asset would download something nobody chose. Windows used
        # to be the example here; it is supported now, and the public gate took
        # `just` from a community feed with nothing pinned until it was.
        with self.assertRaises(RuntimeError) as raised:
            self._asset("Plan9", "sparc")
        self.assertIn("Plan9", str(raised.exception))

    def _asset(self, system: str, machine: str) -> str:
        real_system, real_machine = platform.system, platform.machine
        platform.system = lambda: system
        platform.machine = lambda: machine
        try:
            return bootstrap_just.target_asset()
        finally:
            platform.system, platform.machine = real_system, real_machine


if __name__ == "__main__":
    unittest.main()

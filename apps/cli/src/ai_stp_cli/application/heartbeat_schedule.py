"""Per-user OS wakeups for opted-in installation heartbeats."""

import base64
import getpass
import hashlib
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.database import configured_path
from ai_stp_cli.paths import config_home, data_home
from ai_stp_foundation.ids import is_valid_id


def _name(organization_id: str) -> str:
    if not is_valid_id(organization_id, "organization"):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "a supplied value is not valid for this command"
        )
    installation = hashlib.sha256(str(configured_path().resolve()).encode()).hexdigest()[:12]
    return f"ai-stp-heartbeat-{installation}-{organization_id}"


def _wsl() -> bool:
    return sys.platform == "linux" and bool(os.environ.get("WSL_DISTRO_NAME"))


def _target(organization_id: str) -> tuple[str, list[str]]:
    args = [
        "-m",
        "ai_stp_cli.application.heartbeat_wakeup",
        organization_id,
        str(config_home().resolve()),
        str(data_home().resolve()),
        "1" if os.environ.get("AI_STP_FORCE_FILE_CREDENTIAL_STORE") == "1" else "0",
    ]
    if _wsl():
        distro = os.environ["WSL_DISTRO_NAME"]
        return "wsl.exe", ["-d", distro, "-u", getpass.getuser(), "--", sys.executable, *args]
    if sys.platform == "win32":
        executable = Path(sys.executable).with_name("pythonw.exe")
        if not executable.is_file():
            raise CliFailure(
                "AI_STP_DEPENDENCY_UNAVAILABLE",
                "the windowless Python executable is unavailable",
            )
        return str(executable), args
    return sys.executable, args


def _run(args: list[str]) -> None:
    try:
        subprocess.run(args, check=True, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the operating system heartbeat scheduler is unavailable",
        ) from error


def _powershell(script: str) -> None:
    executable = "powershell.exe" if _wsl() else "powershell"
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    _run([executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded])


def _ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _windows_install(name: str, organization_id: str) -> None:
    executable, args = _target(organization_id)
    argument = subprocess.list2cmdline(args)
    if executable == "wsl.exe":
        command = subprocess.list2cmdline([executable, *args]).replace('"', '""')
        launcher = f'CreateObject("WScript.Shell").Run "{command}", 0, True'
        action = (
            "$directory = Join-Path $env:LOCALAPPDATA 'ai-stp\\heartbeat'; "
            "New-Item -ItemType Directory -Path $directory -Force | Out-Null; "
            f"$launcher = Join-Path $directory {_ps(name + '.vbs')}; "
            f"[IO.File]::WriteAllText($launcher, {_ps(launcher)}, [Text.Encoding]::Unicode); "
            "$action = New-ScheduledTaskAction -Execute (Get-Command 'wscript.exe' "
            "-ErrorAction Stop).Source -Argument ('//B //Nologo \"' + $launcher + '\"'); "
        )
    else:
        action = (
            f"$action = New-ScheduledTaskAction -Execute {_ps(executable)} "
            f"-Argument {_ps(argument)}; "
        )
    script = (
        "$ErrorActionPreference = 'Stop'; "
        f"{action}"
        "$start = (Get-Date).AddMinutes(1); "
        "$trigger = @(0, 30) | ForEach-Object { "
        "New-ScheduledTaskTrigger -Once -At $start.AddSeconds($_) "
        "-RepetitionInterval (New-TimeSpan -Minutes 1) "
        "-RepetitionDuration (New-TimeSpan -Days 3650) }; "
        "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable "
        "-MultipleInstances IgnoreNew; "
        "$principal = New-ScheduledTaskPrincipal "
        "-UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) "
        "-LogonType Interactive -RunLevel Limited; "
        f"Register-ScheduledTask -TaskName {_ps(name)} -Action $action "
        "-Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null"
    )
    _powershell(script)


def _windows_remove(name: str) -> None:
    _powershell(
        "$ErrorActionPreference = 'Stop'; "
        f"if (Get-ScheduledTask -TaskName {_ps(name)} -ErrorAction SilentlyContinue) {{ "
        f"Unregister-ScheduledTask -TaskName {_ps(name)} -Confirm:$false }}; "
        "$directory = Join-Path $env:LOCALAPPDATA 'ai-stp\\heartbeat'; "
        f"$launcher = Join-Path $directory {_ps(name + '.vbs')}; "
        "Remove-Item -LiteralPath $launcher -ErrorAction SilentlyContinue"
    )


def _windows_present(name: str) -> bool:
    executable = "powershell.exe" if _wsl() else "powershell"
    script = (
        f"$task = Get-ScheduledTask -TaskName {_ps(name)} "
        "-ErrorAction SilentlyContinue; "
        "if ($task -and $task.State -ne 'Disabled') { exit 0 } else { exit 1 }"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _mac_path(name: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.aistp.{name}.plist"


def _mac_domain() -> str:
    return f"gui/{os.getuid()}"  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]


def _mac_loaded(name: str) -> bool:
    try:
        result = subprocess.run(
            ["launchctl", "print", f"{_mac_domain()}/com.aistp.{name}"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _mac_install(name: str, organization_id: str) -> None:
    path = _mac_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and _mac_loaded(name):
        _run(["launchctl", "bootout", _mac_domain(), str(path)])
    executable, args = _target(organization_id)
    payload = {
        "Label": f"com.aistp.{name}",
        "ProgramArguments": [executable, *args],
        "StartInterval": 30,
        "RunAtLoad": True,
    }
    path.write_bytes(plistlib.dumps(payload))
    _run(["launchctl", "bootstrap", _mac_domain(), str(path)])


def _mac_remove(name: str) -> None:
    path = _mac_path(name)
    if path.exists():
        if _mac_loaded(name):
            _run(["launchctl", "bootout", _mac_domain(), str(path)])
        path.unlink()


def _linux_paths(name: str) -> tuple[Path, Path]:
    directory = Path.home() / ".config" / "systemd" / "user"
    return directory / f"{name}.service", directory / f"{name}.timer"


def _linux_install(name: str, organization_id: str) -> None:
    service, timer = _linux_paths(name)
    service.parent.mkdir(parents=True, exist_ok=True)
    executable, args = _target(organization_id)
    from shlex import quote

    command = [executable, *args]
    if any("\n" in part or "\r" in part for part in command):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "a supplied value is not valid for this command"
        )

    service.write_text(
        "[Unit]\nDescription=ai-stp installation heartbeat\n"
        "[Service]\nType=oneshot\nExecStart="
        + " ".join(quote(item.replace("%", "%%")) for item in command)
        + "\n",
        encoding="utf-8",
    )
    timer.write_text(
        "[Unit]\nDescription=ai-stp installation heartbeat wakeup\n"
        "[Timer]\nOnCalendar=*-*-* *:*:00,30\nPersistent=true\n"
        f"Unit={name}.service\n"
        "[Install]\nWantedBy=timers.target\n",
        encoding="utf-8",
    )
    _run(["systemctl", "--user", "daemon-reload"])
    _run(["systemctl", "--user", "enable", "--now", timer.name])


def _linux_remove(name: str) -> None:
    service, timer = _linux_paths(name)
    if service.exists() or timer.exists():
        _run(["systemctl", "--user", "disable", "--now", timer.name])
        service.unlink(missing_ok=True)
        timer.unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"])


def install(organization_id: str) -> None:
    name = _name(organization_id)
    if sys.platform == "win32" or _wsl():
        _windows_install(name, organization_id)
    elif sys.platform == "darwin":
        _mac_install(name, organization_id)
    elif sys.platform == "linux":
        _linux_install(name, organization_id)
    else:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the operating system heartbeat scheduler is unavailable",
        )


def remove(organization_id: str) -> None:
    name = _name(organization_id)
    if sys.platform == "win32" or _wsl():
        _windows_remove(name)
    elif sys.platform == "darwin":
        _mac_remove(name)
    elif sys.platform == "linux":
        _linux_remove(name)


def present(organization_id: str) -> bool:
    name = _name(organization_id)
    if sys.platform == "win32" or _wsl():
        return _windows_present(name)
    if sys.platform == "darwin":
        return _mac_path(name).exists() and _mac_loaded(name)
    if sys.platform == "linux":
        if not _linux_paths(name)[1].exists():
            return False
        try:
            return (
                subprocess.run(
                    ["systemctl", "--user", "is-enabled", "--quiet", f"{name}.timer"],
                    capture_output=True,
                    timeout=15,
                    check=False,
                ).returncode
                == 0
            )
        except (OSError, subprocess.SubprocessError):
            return False
    return False

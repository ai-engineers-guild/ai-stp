param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^device_[0-7][0-9A-HJKMNP-TV-Z]{25}$')]
    [string]$DeviceId
)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or
    $env:RUNNER_OS -ne 'Windows' -or [Environment]::OSVersion.Platform -ne 'Win32NT') {
    throw 'Credential-loss fixtures require their disposable hosted Windows user'
}
Add-Type @'
using System.Runtime.InteropServices;
public static class OwnedFixtureCredential {
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
    public static extern bool CredDeleteW(string target, uint type, uint flags);
}
'@
# The pinned windows-native-keyring-store uses user + "." + service by default.
$target = "device-key.$DeviceId.ai-stp-v2"
if (-not [OwnedFixtureCredential]::CredDeleteW($target, 1, 0)) {
    $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    throw "Owned fixture enrollment key deletion failed ($code)"
}

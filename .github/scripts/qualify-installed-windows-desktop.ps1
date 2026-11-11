# Exercise an exact candidate MSI using the Windows accessibility tree.
param(
    [Parameter(Mandatory)][string] $Bundle,
    [Parameter(Mandatory)][string] $Source,
    [Parameter(Mandatory)][string] $Output
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'A disposable hosted Windows runner is required'
}
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$manifest = Get-Content -Raw -LiteralPath (Join-Path $Bundle 'qualified-desktop-Windows.json') | ConvertFrom-Json
if ($manifest.schema_version -ne 1 -or $manifest.platform -cne 'Windows' -or $manifest.source_commit -cne $Source) {
    throw 'Windows package source differs'
}
$msi = @($manifest.files | Where-Object { $_.path -cmatch '^msi/[a-zA-Z0-9_.-]+\.msi$' })
if ($msi.Count -ne 1) { throw 'An exact MSI is required' }
$installer = Join-Path $Bundle $msi[0].path
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant() -cne $msi[0].sha256) {
    throw 'Windows installer digest differs'
}
$installRoot = Join-Path $env:ProgramFiles 'ai-stp-desktop'
if (Test-Path -LiteralPath $installRoot) { throw 'Runner already contains Desktop' }
$installed = Start-Process msiexec.exe -ArgumentList '/i', ('"' + $installer + '"'), '/qn', '/norestart' -Wait -PassThru
if ($installed.ExitCode -ne 0) { throw "MSI installation failed ($($installed.ExitCode))" }
$app = Join-Path $installRoot 'ai-stp-desktop.exe'
$cli = Join-Path $installRoot 'cli\ai-stp-desktop-cli.exe'
if (!(Test-Path -LiteralPath $app -PathType Leaf) -or !(Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw 'Installed Desktop or bundled CLI was not found'
}

function Read-Native([string[]] $Command) {
    $result = & $cli @Command --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or !$result.ok) { throw 'Installed CLI readback failed' }
    return $result.data
}

function Wait-Element([System.Diagnostics.Process] $Process, [string] $Name, $ControlType) {
    $nameCondition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty, $Name
    )
    $condition = $nameCondition
    if ($null -ne $ControlType) {
        $condition = [System.Windows.Automation.AndCondition]::new(
            $nameCondition, [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty, $ControlType
            )
        )
    }
    $deadline = [Diagnostics.Stopwatch]::StartNew()
    while ($deadline.Elapsed.TotalSeconds -lt 45) {
        $Process.Refresh()
        if ($Process.HasExited) { throw 'Installed Desktop exited before UI readiness' }
        if ($Process.MainWindowHandle -ne [IntPtr]::Zero) {
            $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
            $element = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
            if ($null -ne $element -and $element.Current.IsEnabled) { return $element }
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Installed UI element unavailable: $Name"
}

function Open-Settings([System.Diagnostics.Process] $Process) {
    $link = Wait-Element $Process 'Settings' ([System.Windows.Automation.ControlType]::Hyperlink)
    $link.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    $null = Wait-Element $Process 'Local workspace' $null
}

function Close-Desktop([System.Diagnostics.Process] $Process) {
    if (!$Process.CloseMainWindow() -or !$Process.WaitForExit(15000)) {
        throw 'Installed Desktop did not close normally'
    }
}

$version = Read-Native @('version')
if ($version.runtime -cne 'rust' -or $version.wire_schema_version -ne 1) {
    throw 'Installed CLI version contract differs'
}
$doctor = Read-Native @('doctor')
if (@($doctor.checks | Where-Object { $_.name -ceq 'local_identity' -and $_.state -ceq 'needs_user_action' }).Count -ne 1) {
    throw 'First-run Windows workspace is required'
}
$process = Start-Process -FilePath $app -PassThru
try {
    $null = Wait-Element $process "Engine $($version.cli_version)" $null
    Open-Settings $process
    $confirmation = Wait-Element $process 'Initialize or resume this device using the selected credential storage.' (
        [System.Windows.Automation.ControlType]::CheckBox
    )
    $confirmation.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Toggle()
    $initialize = Wait-Element $process 'Initialize workspace' ([System.Windows.Automation.ControlType]::Button)
    $initialize.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    $null = Wait-Element $process 'Initialized' $null
    $identity = (Read-Native @('device', 'show') | ConvertTo-Json -Depth 10 -Compress)
    Close-Desktop $process
    $process = Start-Process -FilePath $app -PassThru
    $null = Wait-Element $process "Engine $($version.cli_version)" $null
    Open-Settings $process
    $null = Wait-Element $process 'Initialized' $null
    if ((Read-Native @('device', 'show') | ConvertTo-Json -Depth 10 -Compress) -cne $identity) {
        throw 'Installed device identity changed after restart'
    }
    Close-Desktop $process
} finally {
    if (!$process.HasExited) { Stop-Process -Id $process.Id }
}

[ordered]@{
    schema_version = 1
    source_sha = $Source
    installer_sha256 = $msi[0].sha256
    app_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash.ToLowerInvariant()
    cli_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $cli).Hash.ToLowerInvariant()
    cli_version = $version.cli_version
    installed_personal_workspace_restart = $true
    corporate_acceptance = $false
    release_authorized = $false
} | ConvertTo-Json | Set-Content -LiteralPath $Output -Encoding ASCII

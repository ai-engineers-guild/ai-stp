# Exercise an exact candidate MSI using the Windows accessibility tree.
param(
    [Parameter(Mandatory)][string] $Bundle,
    [Parameter(Mandatory)][string] $Source,
    [Parameter(Mandatory)][string] $Output
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
trap {
    $location = $_.InvocationInfo.ScriptLineNumber
    if ($_.Exception.Data.Contains('native_controller_source_line')) {
        $location = [int] $_.Exception.Data['native_controller_source_line']
    }
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_FAILURE_V1 ' + $location)
    [Console]::Error.WriteLine('Native owner call site: ' + $_.ScriptStackTrace)
    throw $_
}
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'A disposable hosted Windows runner is required'
}
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required' }
[Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 owner')
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

[Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 installed')

function Read-NativeText([string[]] $Command) {
    $text = (& $cli @Command --json) -join "`n"
    $result = $text | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or !$result.ok) {
        # The closed error code is content-free; messages and details stay private.
        $code = if ($result.error.code -cmatch '^[a-z0-9_.-]{1,64}$') { $result.error.code } else { 'unknown' }
        throw "Installed CLI readback failed ($code)"
    }
    return [pscustomobject]@{ Text = $text; Data = $result.data }
}

function Read-Native([string[]] $Command) {
    return (Read-NativeText $Command).Data
}

function Wait-Element([System.Diagnostics.Process] $Process, [string] $Name, $ControlType, [bool] $AllowDisabled = $false) {
    $callerLine = @(Get-PSCallStack)[1].ScriptLineNumber
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
    if (!$AllowDisabled) {
        $condition = [System.Windows.Automation.AndCondition]::new(
            $condition, [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::IsEnabledProperty, $true
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
            if ($null -ne $element -and ($AllowDisabled -or $element.Current.IsEnabled)) { return $element }
        }
        Start-Sleep -Milliseconds 250
    }
    $failure = [InvalidOperationException]::new("Installed UI element unavailable: $Name")
    $failure.Data['native_controller_source_line'] = $callerLine
    throw $failure
}

function Show-Desktop([System.Diagnostics.Process] $Process) {
    $window = Wait-Observation $Process 'owned native window' ({
        if ($Process.MainWindowHandle -ne [IntPtr]::Zero) {
            return [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
        }
        return $null
    }.GetNewClosure())
    $pattern = Require-Pattern $window ([System.Windows.Automation.WindowPattern]::Pattern) 'application window'
    $pattern.SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Maximized)
    $null = Wait-Observation $Process 'maximized owned native window' ({
        if ($pattern.Current.WindowVisualState -eq [System.Windows.Automation.WindowVisualState]::Maximized) {
            return $true
        }
        return $null
    }.GetNewClosure())
}

function Assert-NormalWorkArea([System.Diagnostics.Process] $Process, [string] $Phase) {
    try {
        $null = Wait-Observation $Process 'normal native window within display work area' ({
            if ($Process.MainWindowHandle -eq [IntPtr]::Zero) { return $null }
            $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
            $pattern = Require-Pattern $window ([System.Windows.Automation.WindowPattern]::Pattern) 'application window'
            if ($pattern.Current.WindowVisualState -eq [System.Windows.Automation.WindowVisualState]::Normal -and
                [NativeDesktopInput]::WindowFitsWorkArea($Process.MainWindowHandle)) { return $true }
            return $null
        }.GetNewClosure())
    } catch {
        $original = $_
        try {
            if ($Phase -cnotin @('initial', 'restored')) { throw 'Unknown geometry phase' }
            $bounds = [NativeDesktopInput]::WindowBounds($Process.MainWindowHandle)
            $area = [NativeDesktopInput]::WorkArea($Process.MainWindowHandle)
            $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
            $pattern = Require-Pattern $window ([System.Windows.Automation.WindowPattern]::Pattern) 'application window'
            $record = [ordered]@{
                schema_version = 1; source_sha = $Source; platform = 'Windows'; phase = $Phase
                coordinate_unit = 'physical_pixels'
                frame = [ordered]@{
                    x = $bounds[0]; y = $bounds[1]
                    width = $bounds[2] - $bounds[0]; height = $bounds[3] - $bounds[1]
                }
                work_areas = @([ordered]@{
                    x = $area[0]; y = $area[1]
                    width = $area[2] - $area[0]; height = $area[3] - $area[1]
                    scale_factor = [NativeDesktopInput]::GetDpiForWindow($Process.MainWindowHandle) / 96.0
                })
                native_window_state = [ordered]@{ visual_state = [int] $pattern.Current.WindowVisualState }
            }
            $bytes = [Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json -Depth 6 -Compress))
            if ($bytes.Length -gt 16384) { throw 'Geometry observation exceeds its bound' }
            $path = Join-Path $env:RUNNER_TEMP 'installed-native-window-geometry.json'
            $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew)
            try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
        } catch { [Console]::Error.WriteLine('Owned native geometry observation unavailable') }
        throw $original
    }
}

function Set-OversizedNormalState([string] $Path, [int[]] $Area) {
    $file = Get-Item -LiteralPath $Path
    if ($file.PSIsContainer -or $file.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint) -or
        $file.Length -gt 65536) { throw 'Owned native window state is not a bounded regular file' }
    $saved = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json -AsHashtable
    if (!$saved.ContainsKey('main') -or !$saved.main.ContainsKey('width') -or
        !$saved.main.ContainsKey('height') -or !$saved.main.ContainsKey('maximized')) {
        throw 'Native window state did not retain its geometry'
    }
    # Simulate the saved normal size of a larger display; preserve every other preference.
    $saved.main.width = [int](2 * ($Area[2] - $Area[0]))
    $saved.main.height = [int](2 * ($Area[3] - $Area[1]))
    $saved.main.maximized = $false
    $saved | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Path -Encoding UTF8
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


$catalogRoot = Join-Path $PSScriptRoot '../../apps/desktop/src/locales'
$languageConfiguration = Get-Content -Raw -LiteralPath (Join-Path $catalogRoot '../localization.json') | ConvertFrom-Json -AsHashtable
$catalogs = @{}
foreach ($locale in $languageConfiguration.languages.Keys) {
    $catalogs[$locale] = Get-Content -Raw -LiteralPath (Join-Path $catalogRoot ($locale + '.json')) | ConvertFrom-Json -AsHashtable
}
Add-Type -Path (Join-Path $PSScriptRoot 'native-desktop-input.cs')

# Failure images contain only the disposable fixture's owned foreground window.
function Save-NativeFailureImage([System.Diagnostics.Process] $Process) {
    $bitmap = $null
    $graphics = $null
    try {
        $Process.Refresh()
        if ($Process.HasExited -or
            [NativeDesktopInput]::GetForegroundWindow() -ne $Process.MainWindowHandle) { return }
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
        $bounds = $window.Current.BoundingRectangle
        $width = [int][Math]::Ceiling($bounds.Width)
        $height = [int][Math]::Ceiling($bounds.Height)
        if ($width -le 0 -or $height -le 0 -or $width -gt 4096 -or $height -gt 4096) { return }
        Add-Type -AssemblyName System.Drawing.Common
        $bitmap = [System.Drawing.Bitmap]::new($width, $height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen(
            [int] $bounds.X, [int] $bounds.Y, 0, 0,
            [System.Drawing.Size]::new($width, $height)
        )
        $bitmap.Save(
            (Join-Path $env:RUNNER_TEMP 'installed-personal-desktop-failure.png'),
            [System.Drawing.Imaging.ImageFormat]::Png
        )
        Write-Host 'Captured the owned fixture window after native refusal'
    } catch {
        Write-Host 'Owned fixture window image unavailable; original refusal retained'
    } finally {
        if ($null -ne $graphics) { $graphics.Dispose() }
        if ($null -ne $bitmap) { $bitmap.Dispose() }
    }
}

function Text([string] $Key, [string] $Locale = 'en') {
    if (!$catalogs.ContainsKey($Locale) -or !$catalogs[$Locale].ContainsKey($Key)) {
        throw 'A required packaged message is unavailable'
    }
    return [string] $catalogs[$Locale][$Key]
}

function Wait-Observation([System.Diagnostics.Process] $Process, [string] $Label, [scriptblock] $Observe) {
    $callerLine = @(Get-PSCallStack)[1].ScriptLineNumber
    $deadline = [Diagnostics.Stopwatch]::StartNew()
    while ($deadline.Elapsed.TotalSeconds -lt 45) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "Installed Desktop exited before $Label" }
        $value = & $Observe
        if ($null -ne $value -and $value -ne $false) { return $value }
        Start-Sleep -Milliseconds 200
    }
    $failure = [InvalidOperationException]::new("Timed out waiting for $Label")
    $failure.Data['native_controller_source_line'] = $callerLine
    throw $failure
}

function Invoke-Control($Element) {
    $node = $Element
    for ($depth = 0; $depth -lt 4 -and $null -ne $node; $depth++) {
        $pattern = $null
        if ($node.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref] $pattern)) {
            $pattern.Invoke()
            return
        }
        if ($node.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref] $pattern)) {
            if ($pattern.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Collapsed) {
                $pattern.Expand()
            }
            return
        }
        $node = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($node)
    }
    throw 'Named UI control has no supported activation action'
}

function Focus-Control([System.Diagnostics.Process] $Process, $Element) {
    if ([NativeDesktopInput]::GetForegroundWindow() -ne $Process.MainWindowHandle -and
        ![NativeDesktopInput]::SetForegroundWindow($Process.MainWindowHandle)) {
        throw 'Owned application could not become foreground'
    }
    $scroll = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref] $scroll)) {
        $scroll.ScrollIntoView()
    }
    $Element.SetFocus()
    $null = Wait-Observation $Process 'owned keyboard focus' ({
        if ([NativeDesktopInput]::GetForegroundWindow() -eq $Process.MainWindowHandle -and
            [System.Windows.Automation.Automation]::Compare(
                [System.Windows.Automation.AutomationElement]::FocusedElement, $Element
            )) { return $true }
        return $null
    }.GetNewClosure())
}

function Click-NativeControl([System.Diagnostics.Process] $Process, $Element) {
    if (!$Element.Current.IsEnabled) { throw 'Native pointer target is disabled' }
    $scroll = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref] $scroll)) {
        $scroll.ScrollIntoView()
    }
    # A page transition can briefly cover the control; the click waits until the
    # point resolves to it, within the shared observation deadline.
    $point = Wait-Observation $Process 'native clickable point on the intended control' ({
        $candidate = $Element.GetClickablePoint()
        $hit = [System.Windows.Automation.AutomationElement]::FromPoint($candidate)
        for ($depth = 0; $depth -lt 6 -and $null -ne $hit; $depth++) {
            if ([System.Windows.Automation.Automation]::Compare($hit, $Element)) { return $candidate }
            $hit = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($hit)
        }
        return $null
    }.GetNewClosure())
    $injected = [NativeDesktopInput]::ClickAt(
        $Process.MainWindowHandle, [int][Math]::Floor($point.X), [int][Math]::Floor($point.Y)
    )
    Write-Host ('Native pointer events accepted: ' + $injected)
}

function Assert-KeyboardFocus([System.Diagnostics.Process] $Process, $Element) {
    if (!$Element.Current.IsEnabled) { throw 'Native keyboard target is disabled' }
    $keyboardOwned = [NativeDesktopInput]::KeyboardFocusOwned($Process.MainWindowHandle)
    $modifiers = [NativeDesktopInput]::PressedModifiers()
    $foregroundOwned = [NativeDesktopInput]::GetForegroundWindow() -eq $Process.MainWindowHandle
    $automationFocused = [System.Windows.Automation.Automation]::Compare(
        [System.Windows.Automation.AutomationElement]::FocusedElement, $Element
    )
    if (!$keyboardOwned -or $modifiers -ne 0 -or !$foregroundOwned -or !$automationFocused) {
        Write-Host ([ordered]@{
            native_keyboard_target = 'refused'
            keyboard_focus_owned = $keyboardOwned
            pressed_modifiers = $modifiers
            foreground_owned = $foregroundOwned
            automation_focused = $automationFocused
        } | ConvertTo-Json -Compress)
        throw 'Native edit lost its owned keyboard target'
    }
}

function Focus-KeyboardLink([System.Diagnostics.Process] $Process, $Target) {
    $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $previous = [System.Windows.Automation.AutomationElement]::FocusedElement
    $seen = [System.Collections.Generic.HashSet[string]]::new()
    for ($step = 1; $step -le 32; $step++) {
        if ([NativeDesktopInput]::GetForegroundWindow() -ne $Process.MainWindowHandle -or
            ![NativeDesktopInput]::KeyboardFocusOwned($Process.MainWindowHandle) -or
            [NativeDesktopInput]::PressedModifiers() -ne 0) {
            throw 'Native navigation has no owned keyboard target'
        }
        $injected = [NativeDesktopInput]::PreviousTab()
        Write-Host ('Native focus traversal keyboard events accepted: ' + $injected)
        $next = Wait-Observation $Process 'actual keyboard focus transition' ({
            $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
            if ($null -eq $focused -or [NativeDesktopInput]::PressedModifiers() -ne 0 -or
                ($null -ne $previous -and [System.Windows.Automation.Automation]::Compare($focused, $previous))) {
                return $null
            }
            $ancestor = $focused
            for ($depth = 0; $depth -lt 64 -and $null -ne $ancestor; $depth++) {
                if ([System.Windows.Automation.Automation]::Compare($ancestor, $window)) {
                    return $focused
                }
                $ancestor = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($ancestor)
            }
            throw 'Native keyboard focus left the owned application'
        }.GetNewClosure())
        if ([System.Windows.Automation.Automation]::Compare($next, $Target)) { return $step }
        $identifier = $next.GetRuntimeId() -join ','
        if (!$seen.Add($identifier)) { throw 'Native keyboard navigation completed a cycle without its link' }
        $previous = $next
    }
    throw 'Native keyboard navigation exceeded its bounded control count'
}

function Assert-KeyboardTarget([System.Diagnostics.Process] $Process, $Element) {
    Assert-KeyboardFocus $Process $Element
    $value = $null
    if (!$Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref] $value) -or
        $value.Current.IsReadOnly) { throw 'Native context edit is not observably editable' }
}

function Read-EditValue($Element) {
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref] $pattern)) {
        return [string] $pattern.Current.Value
    }
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref] $pattern)) {
        $text = $pattern.DocumentRange.GetText(65537)
        if ($text.Length -gt 65536) { throw 'Native edit text exceeds its observation bound' }
        return $text.TrimEnd([char[]] "`r`n")
    }
    $patterns = @($Element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName }) -join ','
    throw ('Native edit has no readable value/text pattern: ' + $patterns)
}


function Write-InputFailure([System.Diagnostics.Process] $Process, $Element, [int] $ExpectedLength, [string] $Before) {
    $record = [ordered]@{
        expected_length = $ExpectedLength; observed_length = $null; unchanged = $null
        automation_focused = $null; foreground_owned = $null
        keyboard_focus_owned = $null; keyboard_focus_is_root = $null; pressed_modifiers = $null
    }
    try {
        $observed = Read-EditValue $Element
        if ($observed.Length -le 65536) {
            $record.observed_length = $observed.Length
            $record.unchanged = $observed -ceq $Before
        }
    } catch {}
    try {
        $record.automation_focused = [System.Windows.Automation.Automation]::Compare(
            [System.Windows.Automation.AutomationElement]::FocusedElement, $Element
        )
    } catch {}
    try { $record.foreground_owned = [NativeDesktopInput]::GetForegroundWindow() -eq $Process.MainWindowHandle } catch {}
    try { $record.keyboard_focus_owned = [NativeDesktopInput]::KeyboardFocusOwned($Process.MainWindowHandle) } catch {}
    try { $record.keyboard_focus_is_root = [NativeDesktopInput]::KeyboardFocusIsRoot($Process.MainWindowHandle) } catch {}
    try { $record.pressed_modifiers = [NativeDesktopInput]::PressedModifiers() } catch {}
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_INPUT_V1 ' + ($record | ConvertTo-Json -Compress))
}

function Enter-Context(
    [System.Diagnostics.Process] $Process, [string] $Label,
    [string] $FieldKey = 'profiles.contextLabel', [bool] $CountReplacement = $true
) {
    if ($Label -cnotmatch '^[\x20-\x7e]{1,120}$' -or
        ($FieldKey -ceq 'profiles.contextLabel' -and $Label -cnotmatch '^[A-Za-z0-9 ]{1,120}$')) {
        throw 'Unexpected keyboard fixture text'
    }
    $field = Wait-Element $Process (Text $FieldKey) ([System.Windows.Automation.ControlType]::Edit)
    Focus-Control $Process $field
    Click-NativeControl $Process $field
    Assert-KeyboardTarget $Process $field
    $before = Read-EditValue $field
    if ($before.Length -gt 0) {
        $text = $null
        if (!$field.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref] $text) -or
            $text.SupportedTextSelection -eq [System.Windows.Automation.SupportedTextSelection]::None) {
            throw 'Native context edit cannot expose its text selection'
        }
        $injected = [NativeDesktopInput]::SelectAll()
        Write-Host ('Native selection keyboard events accepted: ' + $injected)
        $null = Wait-Observation $Process 'complete context text selection' ({
            $ranges = @($text.GetSelection())
            if ($ranges.Count -eq 1 -and $null -ne $ranges[0] -and
                $ranges[0].GetText(65537).TrimEnd([char[]] "`r`n") -ceq $before -and
                (Read-EditValue $field) -ceq $before -and
                [NativeDesktopInput]::PressedModifiers() -eq 0) { return $true }
            return $null
        }.GetNewClosure())
        Assert-KeyboardTarget $Process $field
        Write-Host ([ordered]@{
            native_text_clear = 'before_keyboard'
            keyboard_api = 'SendInput_SCANCODE'
            keyboard_focus_owned = [NativeDesktopInput]::KeyboardFocusOwned($Process.MainWindowHandle)
            pressed_modifiers = [NativeDesktopInput]::PressedModifiers()
            initial_length = $before.Length
            enabled = $field.Current.IsEnabled
            read_only = $field.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.IsReadOnly
            selection_ranges = @($text.GetSelection()).Count
            foreground_owned = [NativeDesktopInput]::GetForegroundWindow() -eq $Process.MainWindowHandle
        } | ConvertTo-Json -Compress)
        $injected = [NativeDesktopInput]::Backspace()
        Write-Host ('Native clear keyboard events accepted: ' + $injected)
        try {
            $null = Wait-Observation $Process 'cleared context label' ({
                if ((Read-EditValue $field) -ceq '') { return $true }
                return $null
            }.GetNewClosure())
        } catch {
            $observed = Read-EditValue $field
            $ranges = @($text.GetSelection())
            Write-Host ([ordered]@{
                native_text_clear = 'refused'
                keyboard_focus_owned = [NativeDesktopInput]::KeyboardFocusOwned($Process.MainWindowHandle)
                pressed_modifiers = [NativeDesktopInput]::PressedModifiers()
                initial_length = $before.Length
                observed_length = $observed.Length
                enabled = $field.Current.IsEnabled
                read_only = $field.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.IsReadOnly
                unchanged = $observed -ceq $before
                selection_ranges = $ranges.Count
                foreground_owned = [NativeDesktopInput]::GetForegroundWindow() -eq $Process.MainWindowHandle
            } | ConvertTo-Json -Compress)
            throw
        }
        if ($CountReplacement) { $script:contextTextReplacements++ }
    }
    Assert-KeyboardTarget $Process $field
    $injected = [NativeDesktopInput]::TypeText($Label)
    Write-Host ('Native text keyboard events accepted: ' + $injected)
    try {
        $null = Wait-Observation $Process 'entered context label' ({
            if ((Read-EditValue $field) -ceq $Label) { return $true }
            return $null
        }.GetNewClosure())
    } catch {
        $originalFailure = $_
        try { Write-InputFailure $Process $field $Label.Length $before } catch {
            [Console]::Error.WriteLine('Owned native input diagnostic unavailable')
        }
        throw $originalFailure
    }
}

function Read-PublicPlan(
    [System.Diagnostics.Process] $Process, [string] $Locale = 'en',
    [string] $RegionKey = 'profiles.reviewNativeProfilePlan'
) {
    $region = Wait-Element $Process (Text $RegionKey $Locale) $null $true
    return Wait-Observation $Process 'exact public profile plan' ({
        $nodes = $region.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        if ($nodes.Count -gt 2500) { throw 'Native review tree exceeds its observation bound' }
        $raw = $null
        $plan = $null
        $digest = $null
        foreach ($node in $nodes) {
            $values = [System.Collections.Generic.List[string]]::new()
            $values.Add($node.Current.Name)
            $pattern = $null
            if ($node.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref] $pattern)) {
                $values.Add($pattern.Current.Value)
            }
            if ($node.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref] $pattern)) {
                $values.Add($pattern.DocumentRange.GetText(65537))
            }
            foreach ($value in $values) {
                if ($null -eq $value -or $value.Length -gt 65536) { continue }
                if ($value -cmatch '^sha256:[0-9a-f]{64}$') { $digest = $value }
                try { $document = ConvertFrom-Json -InputObject $value -AsHashtable } catch { continue }
                if ($document -is [System.Collections.IDictionary] -and (
                    ($document.Contains('change') -and
                        $document.change -is [System.Collections.IDictionary] -and
                        ($document.change.Contains('context') -or $document.change.Contains('snapshot'))) -or
                    ($document.Contains('connection_id') -and $document.Contains('origin') -and
                        $document.Contains('label'))
                )) {
                    $plan = $document
                    $raw = $value
                }
            }
        }
        if ($null -ne $raw -and $null -ne $digest) {
            return [pscustomobject]@{ Raw = $raw; Digest = $digest; Document = $plan }
        }
        return $null
    }.GetNewClosure())
}

function Read-Review([System.Diagnostics.Process] $Process, [string] $Locale = 'en') {
    $public = Read-PublicPlan $Process $Locale
    if (!$public.Document.Contains('change') -or
        !$public.Document.change.Contains('context')) {
        throw 'Displayed profile review does not contain a context plan'
    }
    return [pscustomobject]@{
        Raw = $public.Raw
        Digest = $public.Digest
        Context = $public.Document.change.context
        Action = $public.Document.change.action
    }
}

function Assert-Review($Review, [string] $Action, [string] $Label, [string] $Identifier = '') {
    if ($Review.Action -cne $Action -or $Review.Context.label -cne $Label -or
        $Review.Context.authority.kind -cne 'local' -or
        $Review.Context.context_id -isnot [string] -or !$Review.Context.context_id -or
        $Review.Context.context_id.Length -gt 512) {
        throw 'Displayed context plan changed intent or authority'
    }
    if ($Identifier -and $Review.Context.context_id -cne $Identifier) {
        throw 'Displayed context plan changed identity'
    }
    return $Review.Context.context_id
}

function Confirm-ExactReview(
    [System.Diagnostics.Process] $Process, [string] $CheckKey, [string] $ApplyKey
) {
    $confirmation = Wait-Element $Process (Text $CheckKey) ([System.Windows.Automation.ControlType]::CheckBox)
    $toggle = Require-Pattern $confirmation ([System.Windows.Automation.TogglePattern]::Pattern) 'native review confirmation'
    if ($toggle.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::Off) {
        throw 'Native review was already confirmed'
    }
    $apply = Wait-Element $Process (Text $ApplyKey) ([System.Windows.Automation.ControlType]::Button) $true
    if ($apply.Current.IsEnabled) { throw 'Unconfirmed native review was applicable' }
    $toggle.Toggle()
    Invoke-Control (Wait-Element $Process (Text $ApplyKey) ([System.Windows.Automation.ControlType]::Button))
}

function Confirm-Review([System.Diagnostics.Process] $Process) {
    Confirm-ExactReview $Process 'profiles.iReviewedThisExactPlanAndAuthorizeThisLocal' 'profiles.applyReviewedChange'
    $null = Wait-Observation $Process 'context review completion' ({
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
        $condition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty, (Text 'profiles.reviewNativeProfilePlan')
        )
        $working = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            (Text 'profiles.workingThroughTheNativeEngine')
        )
        if ($null -eq $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition) -and
            $null -eq $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $working)) {
            return $true
        }
        return $null
    }.GetNewClosure())
}

function New-ContextReview([System.Diagnostics.Process] $Process, [string] $Label) {
    Enter-Context $Process $Label
    Invoke-Control (Wait-Element $Process (Text 'profiles.reviewContextCreation') ([System.Windows.Automation.ControlType]::Button))
    Invoke-Control (Wait-Element $Process (Text 'profiles.exactPublicPlan') $null $true)
    $review = Read-Review $Process
    $null = Assert-Review $review 'create' $Label
    return $review
}

function Assert-SelectedContext([System.Diagnostics.Process] $Process, [string] $Identifier) {
    $null = Wait-Observation $Process 'selected native context' ({
        $listed = Read-Native @('context', 'list')
        if ($null -ne $listed.selected -and $listed.selected.context_id -ceq $Identifier) { return $true }
        return $null
    }.GetNewClosure())
}

function Select-Context([System.Diagnostics.Process] $Process, [string] $Label, [string] $Identifier) {
    Invoke-Control (Wait-Element $Process (Text 'profiles.reviewViewSelection') ([System.Windows.Automation.ControlType]::Button))
    Invoke-Control (Wait-Element $Process (Text 'profiles.exactPublicPlan') $null $true)
    $null = Assert-Review (Read-Review $Process) 'select' $Label $Identifier
    Confirm-Review $Process
    Assert-SelectedContext $Process $Identifier
    $null = Wait-Element $Process ($Label + (Text 'profiles.selectedView')) $null
}

function Require-Pattern($Element, $Pattern, [string] $Label) {
    $value = $null
    if ($Element.TryGetCurrentPattern($Pattern, [ref] $value)) { return $value }
    $supported = @($Element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName }) -join ','
    $failure = [InvalidOperationException]::new(
        "Native $Label has no " + $Pattern.ProgrammaticName + '; supported=' + $supported
    )
    $failure.Data['native_controller_source_line'] = @(Get-PSCallStack)[1].ScriptLineNumber
    $failure.Data['native_controller_pattern_missing'] = $true
    throw $failure
}

function Wait-PreferenceReady([System.Diagnostics.Process] $Process, [string] $Locale) {
    $selector = Wait-Element $Process (Text 'language.label' $Locale) ([System.Windows.Automation.ControlType]::ComboBox)
    $group = Wait-Element $Process (Text 'language.label' $Locale) ([System.Windows.Automation.ControlType]::Group) $true
    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty, (Text 'status.applying' $Locale)
    )
    $null = Wait-Observation $Process 'acknowledged native appearance preferences' ({
        if ($null -eq $group.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)) {
            return $true
        }
        return $null
    }.GetNewClosure())
    return $selector
}

function Select-Language([System.Diagnostics.Process] $Process, [string] $Previous, [string] $Next) {
    $selector = Wait-PreferenceReady $Process $Previous
    if ($Previous -cne $Next) {
        $name = [string] $languageConfiguration.languages[$Next].name
        if ($Next -ceq 'kk') { $name += ' · ' + $languageConfiguration.languages[$Next].shortName }
        Focus-Control $Process $selector
        $null = Wait-Observation $Process 'visible native language selector' ({
            if (!$selector.Current.IsOffscreen) { return $true }
            return $null
        }.GetNewClosure())
        $expand = Require-Pattern $selector ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) 'language selector'
        [Console]::Error.WriteLine('Native locale ' + $Previous + ' -> ' + $Next +
            '; initial_state=' + $expand.Current.ExpandCollapseState)
        if ($expand.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Collapsed) {
            throw 'Native language selector is not initially collapsed'
        }
        Click-NativeControl $Process $selector
        try {
            $null = Wait-Observation $Process 'expanded native language selector' ({
                if ($expand.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Expanded -and
                    [NativeDesktopInput]::PointerButtonsReleased()) { return $true }
                return $null
            }.GetNewClosure())
        } catch {
            Write-Host ([ordered]@{
                native_combo_open = 'refused'
                enabled = $selector.Current.IsEnabled
                state = [string] $expand.Current.ExpandCollapseState
                keyboard_focus_owned = [NativeDesktopInput]::KeyboardFocusOwned($Process.MainWindowHandle)
                pressed_modifiers = [NativeDesktopInput]::PressedModifiers()
                foreground_owned = [NativeDesktopInput]::GetForegroundWindow() -eq $Process.MainWindowHandle
            } | ConvertTo-Json -Compress)
            throw
        }
        $option = Wait-Observation $Process 'packaged native language option' ({
            $condition = [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::NameProperty, $name
            )
            return $selector.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
        }.GetNewClosure())
        $selection = Require-Pattern $option ([System.Windows.Automation.SelectionItemPattern]::Pattern) 'language option'
        $selection.Select()
        $selector = Wait-Element $Process (Text 'language.label' $Next) ([System.Windows.Automation.ControlType]::ComboBox)
        $expand = Require-Pattern $selector ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) 'language selector'
        if ($expand.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Expanded) {
            $expand.Collapse()
        }
        $null = Wait-Observation $Process 'closed native language selector' ({
            if ($expand.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Collapsed -and
                [NativeDesktopInput]::PointerButtonsReleased()) { return $true }
            return $null
        }.GetNewClosure())
    }
    $null = Wait-PreferenceReady $Process $Next
}

function Set-Theme([System.Diagnostics.Process] $Process, [string] $Locale, [bool] $Dark) {
    $key = if ($Dark) { 'shell.light' } else { 'shell.dark' }
    $other = if ($Dark) { 'shell.dark' } else { 'shell.light' }
    $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty, (Text $key $Locale)
    )
    if ($null -eq $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)) {
        Invoke-Control (Wait-Element $Process (Text $other $Locale) ([System.Windows.Automation.ControlType]::Button))
    }
    $null = Wait-Element $Process (Text $key $Locale) ([System.Windows.Automation.ControlType]::Button)
    $null = Wait-PreferenceReady $Process $Locale
}

function Assert-Sidebar([System.Diagnostics.Process] $Process, [string] $Locale) {
    $null = Wait-Observation $Process 'native sidebar direction' ({
        $control = Wait-Element $Process (Text 'language.label' $Locale) ([System.Windows.Automation.ControlType]::ComboBox)
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
        $bounds = $control.Current.BoundingRectangle
        $frame = $window.Current.BoundingRectangle
        if ($bounds.Width -le 0 -or $frame.Width -le 0) { return $null }
        $right = $bounds.X + $bounds.Width / 2 -gt $frame.X + $frame.Width / 2
        if ($right -eq ($languageConfiguration.languages[$Locale].direction -ceq 'rtl')) { return $true }
        return $null
    }.GetNewClosure())
}


function Write-OptionFailure($Selector, $Option, [string] $Name, $Failure) {
    $record = [ordered]@{
        hresult = '00000000'; missing_pattern = $false; control_type = $null
        enabled = $null; offscreen = $null; selection_item = $null; invoke = $null
        selected_after = $null
    }
    $exception = $Failure.Exception
    for ($depth = 0; $depth -lt 8 -and $null -ne $exception; $depth++) {
        $record.hresult = $exception.HResult.ToString('X8')
        if ($exception.Data.Contains('native_controller_pattern_missing') -and
            $exception.Data['native_controller_pattern_missing'] -eq $true) {
            $record.missing_pattern = $true
        }
        $exception = $exception.InnerException
    }
    try { $record.control_type = $Option.Current.ControlType.Id } catch {}
    try { $record.enabled = $Option.Current.IsEnabled } catch {}
    try { $record.offscreen = $Option.Current.IsOffscreen } catch {}
    foreach ($property in @(
        @('selection_item', [System.Windows.Automation.AutomationElement]::IsSelectionItemPatternAvailableProperty),
        @('invoke', [System.Windows.Automation.AutomationElement]::IsInvokePatternAvailableProperty)
    )) {
        try {
            $observed = $Option.GetCurrentPropertyValue($property[1])
            if ($observed -is [bool]) { $record[$property[0]] = $observed }
        } catch {}
    }
    try {
        $pattern = $null
        if ($Selector.TryGetCurrentPattern([System.Windows.Automation.SelectionPattern]::Pattern, [ref] $pattern)) {
            $chosen = @($pattern.Current.GetSelection())
            $record.selected_after = $chosen.Count -eq 1 -and $chosen[0].Current.Name -ceq $Name
        }
    } catch {}
    [Console]::Out.WriteLine(
        'AI_STP_NATIVE_DESKTOP_OPTION_V1 ' + ($record | ConvertTo-Json -Compress)
    )
}

function Select-ProfileOption([System.Diagnostics.Process] $Process, [string] $Key, [string] $Name) {
    $selectorCallerLine = @(Get-PSCallStack)[1].ScriptLineNumber
    try {
        $selector = Wait-Element $Process (Text $Key) ([System.Windows.Automation.ControlType]::ComboBox)
        Focus-Control $Process $selector
        $null = Wait-Observation $Process 'visible owned native profile selector' ({
            if (!$selector.Current.IsOffscreen) { return $true }
            return $null
        }.GetNewClosure())
    } catch {
        $_.Exception.Data['native_controller_source_line'] = $selectorCallerLine
        # Only this first selector precedes every account enrollment and login.
        # A failed guard cannot publish an image or replace the original refusal.
        if ($Key -ceq 'profiles.signInMethod') {
            try {
                $connections = Read-Native @('account', 'connections', 'list')
                if (@($connections.connections).Count -eq 0) { Save-NativeFailureImage $Process }
            } catch {
                [Console]::Error.WriteLine('Pre-authentication image guard refused')
            }
        }
        # Publish only closed classifications; the UI tree and error text stay private.
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
        $details = $window.FindFirst(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::NameProperty, (Text 'error.engineDetails')
            )
        )
        if ($null -ne $details) { Invoke-Control $details }
        $nodes = $window.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        if ($nodes.Count -gt 2500) { throw 'Native selector observation exceeds its bound' }
        $checkpoint = 'profile_selector_absent'
        foreach ($node in $nodes) {
            $name = $node.Current.Name
            if ($name -ceq (Text $Key)) {
                $checkpoint = if ($node.Current.ControlType -eq [System.Windows.Automation.ControlType]::ComboBox) {
                    'profile_selector_disabled'
                } else { 'profile_selector_role' }
            }
        }
        $classifications = [ordered]@{
            'IPC_THROW' = 'discovery_ipc'
            'AI_STP_VALIDATION_ERROR' = 'discovery_validation'
            'AI_STP_NOT_FOUND' = 'discovery_not_found'
            'AI_STP_PRECONDITION_FAILED' = 'discovery_precondition'
            'AI_STP_CONFLICT' = 'discovery_conflict'
            'AI_STP_DEPENDENCY_UNAVAILABLE' = 'discovery_unavailable'
            'AI_STP_INTERNAL' = 'discovery_internal'
            (Text 'profiles.noSignInMethodsSupportedByThisEngineAre') = 'discovery_no_provider'
        }
        foreach ($node in $nodes) {
            if ($classifications.Contains($node.Current.Name)) {
                $checkpoint = $classifications[$node.Current.Name]
                break
            }
        }
        [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 ' + $checkpoint)
        throw
    }
    $expand = Require-Pattern $selector ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) 'profile selector'
    if ($expand.Current.ExpandCollapseState -ne [System.Windows.Automation.ExpandCollapseState]::Collapsed) {
        throw 'Native profile selector was not initially collapsed'
    }
    Click-NativeControl $Process $selector
    $null = Wait-Observation $Process 'expanded native profile selector' ({
        if ($expand.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Expanded -and
            [NativeDesktopInput]::PointerButtonsReleased()) { return $true }
        return $null
    }.GetNewClosure())
    $option = Wait-Observation $Process 'owned native profile option' ({
        $condition = [System.Windows.Automation.AndCondition]::new(
            [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::NameProperty, $Name
            ),
            [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::IsEnabledProperty, $true
            ),
            [System.Windows.Automation.OrCondition]::new(
                [System.Windows.Automation.PropertyCondition]::new(
                    [System.Windows.Automation.AutomationElement]::IsSelectionItemPatternAvailableProperty, $true
                ),
                [System.Windows.Automation.PropertyCondition]::new(
                    [System.Windows.Automation.AutomationElement]::IsInvokePatternAvailableProperty, $true
                )
            )
        )
        return $selector.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
    }.GetNewClosure())
    # Native options can expose a default action without a selection-state provider.
    try {
        $selection = $null
        if ($option.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref] $selection)) {
            $selection.Select()
        } else {
            (Require-Pattern $option ([System.Windows.Automation.InvokePattern]::Pattern) 'profile option').Invoke()
        }
    } catch {
        $originalFailure = $_
        if (!$originalFailure.Exception.Data.Contains('native_controller_source_line')) {
            $originalFailure.Exception.Data['native_controller_source_line'] = $originalFailure.InvocationInfo.ScriptLineNumber
        }
        try { Write-OptionFailure $selector $option $Name $originalFailure } catch {
            [Console]::Error.WriteLine('Owned native option diagnostic unavailable')
        }
        throw $originalFailure
    }
    if ($expand.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Expanded) {
        $expand.Collapse()
    }
    $null = Wait-Observation $Process 'closed native profile selector' ({
        if ($expand.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Collapsed -and
            [NativeDesktopInput]::PointerButtonsReleased()) { return $true }
        return $null
    }.GetNewClosure())
}

function Read-CorporateFixture {
    if (!$env:AI_STP_NATIVE_DESKTOP_FIXTURE) { return $null }
    $path = [IO.Path]::GetFullPath($env:AI_STP_NATIVE_DESKTOP_FIXTURE)
    $root = [IO.Path]::GetFullPath($env:RUNNER_TEMP) + [IO.Path]::DirectorySeparatorChar
    $file = Get-Item -LiteralPath $path
    if (!$path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -or
        $file.PSIsContainer -or $file.LinkType -or $file.Length -gt 16384) {
        throw 'Native corporate fixture file is not owned and bounded'
    }
    $value = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json -AsHashtable
    if ($value.Count -ne 10 -or $value.protocol -cne 'ai-stp-native-desktop-fixture/1' -or
        $value.nonce -cnotmatch '^[0-9a-f]{64}$' -or $value.source_sha -cne $Source -or
        $value.origin -cnotmatch '^http://127[.]0[.]0[.]1:[1-9][0-9]{0,4}$' -or
        [IO.Path]::GetFullPath($value.result_path) -cne (Join-Path $file.DirectoryName 'native-corporate-journey.json')) {
        throw 'Native corporate fixture contract differs'
    }
    foreach ($key in @('account_id', 'organization_id', 'project_id')) {
        if ($value[$key] -isnot [string] -or $value[$key].Length -lt 1 -or $value[$key].Length -gt 128) {
            throw 'Native corporate fixture identity is invalid'
        }
    }
    if ([IO.Path]::GetFullPath($value.checkout_root) -cne (Join-Path $file.DirectoryName 'checkout') -or
        ![IO.Path]::IsPathFullyQualified($value.git_executable) -or
        !(Test-Path -LiteralPath $value.git_executable -PathType Leaf)) {
        throw 'Native corporate checkout fixture differs'
    }
    if (Test-Path -LiteralPath $value.result_path) { throw 'Native corporate result already exists' }
    return $value
}

function Assert-RemoteReview($Review, $Fixture, [string] $Action, [string] $Connection, [string] $Identifier = '') {
    $authority = $Review.Context.authority
    if ($Review.Action -cne $Action -or $Review.Context.label -cne 'Native corporate context' -or
        $authority.kind -cne 'remote' -or $authority.organization.organization_id -cne $Fixture.organization_id -or
        $authority.account.account_id -cne $Fixture.account_id -or
        $authority.account.origin -cne $Fixture.origin -or
        $authority.account.connection.connection_id -cne $Connection -or
        $Review.Context.context_id -isnot [string] -or !$Review.Context.context_id) {
        throw 'Displayed corporate plan changed intent or authority'
    }
    if ($Identifier -and $Review.Context.context_id -cne $Identifier) {
        throw 'Displayed corporate plan changed context identity'
    }
    return $Review.Context.context_id
}

function Invoke-CorporateApproval($Fixture, [string] $Code) {
    if (!$Code -or $Code.Length -gt 128) { throw 'Native approval code is invalid' }
    $request = [ordered]@{
        protocol = $Fixture.protocol; nonce = $Fixture.nonce; sequence = 1
        action = 'approve_device'; user_code = $Code
    }
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_FIXTURE_V1 ' + ($request | ConvertTo-Json -Compress))
    [Console]::Out.Flush()
    $line = [Console]::In.ReadLine()
    if ($null -eq $line -or $line.Length -gt 4096) { throw 'Native approval response exceeded its bound' }
    $reply = ConvertFrom-Json -InputObject $line -AsHashtable
    if ($reply.Count -ne 4 -or $reply.protocol -cne $Fixture.protocol -or
        $reply.nonce -cne $Fixture.nonce -or $reply.sequence -ne 1 -or $reply.approved -ne $true) {
        throw 'Native approval response differs'
    }
}

function Assert-CorporateSession($Fixture, [string] $Connection) {
    $status = Read-Native @('account', 'status', '--connection', $Connection)
    if ($status.origin -cne $Fixture.origin -or $status.session.state -cne 'authorized' -or
        $status.session.account_id -cne $Fixture.account_id) {
        throw 'Original corporate account session changed'
    }
}

function Test-CorporateJourney([System.Diagnostics.Process] $Process, $Fixture, [string] $Identity) {
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 connection')
    Invoke-Control (Wait-Element $Process (Text 'shell.connections') ([System.Windows.Automation.ControlType]::Hyperlink))
    Enter-Context $Process 'Native company connection' 'profiles.connectionLabel' $false
    Enter-Context $Process $Fixture.origin 'profiles.serverOrigin' $false
    $discovery = Wait-Element $Process (Text 'profiles.checkServerSignInMethods') ([System.Windows.Automation.ControlType]::Button)
    Focus-Control $Process $discovery
    Click-NativeControl $Process $discovery
    Select-ProfileOption $Process 'profiles.signInMethod' 'github'
    Invoke-Control (Wait-Element $Process (Text 'profiles.reviewConnectionCreation') ([System.Windows.Automation.ControlType]::Button))
    Invoke-Control (Wait-Element $Process (Text 'profiles.exactPublicPlan') $null $true)
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 connection')
    $plan = Read-PublicPlan $Process
    if ($plan.Document.label -cne 'Native company connection' -or $plan.Document.origin -cne $Fixture.origin -or
        $plan.Document.provider -cne 'github' -or $plan.Document.connection_id -isnot [string] -or
        !$plan.Document.connection_id) { throw 'Displayed connection plan changed intent' }
    $connection = $plan.Document.connection_id
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 connection_reviewed')
    Confirm-Review $Process
    $stored = @((Read-Native @('account', 'connections', 'list')).connections |
        Where-Object { $_.connection_id -ceq $connection })
    if ($stored.Count -ne 1 -or $stored[0].state -cne 'ready' -or
        $stored[0].label -cne 'Native company connection' -or
        $stored[0].origin -cne $Fixture.origin -or $stored[0].provider -cne 'github') {
        throw 'Stored connection changed the reviewed intent'
    }
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 connection_saved')
    Invoke-Control (Wait-Element $Process (Text 'profiles.openThisAccountSession') ([System.Windows.Automation.ControlType]::Hyperlink))
    $provider = Wait-Element $Process 'GitHub' ([System.Windows.Automation.ControlType]::Button)
    $toggle = Require-Pattern $provider ([System.Windows.Automation.TogglePattern]::Pattern) 'sign-in provider'
    if ($toggle.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::Indeterminate) {
        throw 'Native sign-in provider has an invalid toggle state'
    }
    if ($toggle.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::Off) { $toggle.Toggle() }
    $null = Wait-Observation $Process 'selected native sign-in provider' ({
        if ($toggle.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On) { return $true }
        return $null
    }.GetNewClosure())
    Invoke-Control (Wait-Element $Process (Text 'auth.startSignIn') ([System.Windows.Automation.ControlType]::Button))
    $null = Wait-Element $Process (Text 'auth.approveThisDeviceInYourBrowser') $null
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 pending')
    $pending = (Read-Native @('account', 'status', '--connection', $connection)).session
    if ($pending.state -cne 'pending' -or $pending.user_code -isnot [string]) { throw 'Native sign-in did not retain a pending confirmation' }
    Invoke-Control (Wait-Element $Process (Text 'shell.connections') ([System.Windows.Automation.ControlType]::Hyperlink))
    Invoke-Control (Wait-Element $Process (Text 'profiles.openThisAccountSession') ([System.Windows.Automation.ControlType]::Hyperlink))
    $null = Wait-Element $Process (Text 'auth.approveThisDeviceInYourBrowser') $null
    $again = (Read-Native @('account', 'status', '--connection', $connection)).session
    if ($again.state -cne 'pending' -or $again.user_code -cne $pending.user_code) {
        throw 'Navigation replaced the original pending confirmation'
    }
    $null = Wait-Observation $Process 'original pending confirmation displayed' ({
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
        $condition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty, $pending.user_code
        )
        if ($null -ne $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)) { return $true }
        return $null
    }.GetNewClosure())
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 approval')
    Invoke-CorporateApproval $Fixture $pending.user_code
    Invoke-Control (Wait-Element $Process (Text 'auth.openBrowserAndConfirm') ([System.Windows.Automation.ControlType]::Button))
    $null = Wait-Element $Process (Text 'auth.signedIn') $null
    Assert-CorporateSession $Fixture $connection
    Invoke-Control (Wait-Element $Process (Text 'shell.connections') ([System.Windows.Automation.ControlType]::Hyperlink))
    Enter-Context $Process 'Native corporate draft' 'profiles.contextLabel' $false
    Enter-Context $Process 'Native corporate context' 'profiles.contextLabel' $false
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 context_connection')
    Select-ProfileOption $Process 'profiles.contextConnection' ('Native company connection · ' + $Fixture.origin)
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 organization')
    Invoke-Control (Wait-Element $Process (Text 'profiles.readAvailableOrganizations') ([System.Windows.Automation.ControlType]::Button))
    Select-ProfileOption $Process 'profiles.organization' 'Installed fixture company · corporate'
    Invoke-Control (Wait-Element $Process (Text 'profiles.reviewContextCreation') ([System.Windows.Automation.ControlType]::Button))
    Invoke-Control (Wait-Element $Process (Text 'profiles.exactPublicPlan') $null $true)
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 context')
    $review = Read-Review $Process
    $context = Assert-RemoteReview $review $Fixture 'create' $connection
    $device = $review.Context.authority.account.device_id
    Confirm-Review $Process
    $listed = Read-Native @('context', 'list')
    if (@($listed.contexts).Count -ne 3 -or
        @($listed.contexts | Where-Object { $_.context.authority.kind -ceq 'local' }).Count -ne 2) {
        throw 'Personal and corporate contexts did not coexist'
    }
    $card = Wait-Element $Process 'Native corporate context' ([System.Windows.Automation.ControlType]::Group) $true
    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty, (Text 'profiles.reviewViewSelection')
    )
    $button = Wait-Observation $Process 'owned corporate context selection' ({
        $candidate = $card.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
        if ($null -ne $candidate -and $candidate.Current.IsEnabled) { return $candidate }
        return $null
    }.GetNewClosure())
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 selection')
    Invoke-Control $button
    Invoke-Control (Wait-Element $Process (Text 'profiles.exactPublicPlan') $null $true)
    $null = Assert-RemoteReview (Read-Review $Process) $Fixture 'select' $connection $context
    Confirm-Review $Process
    Assert-SelectedContext $Process $context
    if ($device -isnot [string] -or !$device) { throw 'Corporate context did not resolve its enrolled device' }
    if ((Read-Native @('device', 'show') | ConvertTo-Json -Depth 10 -Compress) -cne $Identity) {
        throw 'Corporate sign-in replaced the original native identity'
    }
    return [pscustomobject]@{ Context = $context; Connection = $connection; Device = $device }
}


function Assert-CheckoutIntent(
    $Public, $Fixture, $Corporate, [string] $Action, [string] $Request = ''
) {
    $plan = $Public.Document
    $snapshot = $plan.change.snapshot
    if ($plan.operation_id -isnot [string] -or !$plan.operation_id -or $plan.operation_id.Length -gt 128 -or
        $plan.change.action -cne $Action -or $snapshot.context.context_id -cne $Corporate.Context -or
        $snapshot.account.origin -cne $Fixture.origin -or $snapshot.account.account_id -cne $Fixture.account_id -or
        $snapshot.account.device_id -cne $Corporate.Device -or
        $snapshot.account.connection.connection_id -cne $Corporate.Connection -or
        $snapshot.organization.organization_id -cne $Fixture.organization_id -or
        $snapshot.target.remote_project_id -cne $Fixture.project_id -or
        $snapshot.local_project.local_project_id -isnot [string] -or !$snapshot.local_project.local_project_id -or
        @($snapshot.local_project.root.identity).Count -ne 2) {
        throw 'Displayed checkout plan changed its original authority'
    }
    foreach ($path in @($plan.checkout_root, $snapshot.local_project.root.path)) {
        if ($path.utf8_base64 -isnot [string] -or $path.utf8_base64.Length -gt 43692 -or
            [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($path.utf8_base64)) -cne $Fixture.checkout_root -or
            $path.display -cne $Fixture.checkout_root.Normalize([Text.NormalizationForm]::FormC)) {
            throw 'Displayed checkout plan changed its physical path'
        }
    }
    if ($Request -and $plan.change.request_operation_id -cne $Request) {
        throw 'Displayed checkout plan replaced the original request'
    }
    return [pscustomobject]@{ Operation = $plan.operation_id; Local = $snapshot.local_project.local_project_id }
}

function Start-CorporateCheckout([System.Diagnostics.Process] $Process, $Fixture, $Corporate) {
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 checkout_preview')
    # Fixture preparation uses the installed public engine, never application IPC.
    $preparedText = Read-NativeText @('project', 'passport', 'plan', '--root', $Fixture.checkout_root)
    $prepared = $preparedText.Data
    $local = $prepared.plan.operation.passport.stable_id
    if ($prepared.plan_digest -cnotmatch '^sha256:[0-9a-f]{64}$' -or $local -isnot [string] -or !$local) {
        throw 'Owned checkout passport preparation differs'
    }
    $preparation = Join-Path ([IO.Path]::GetDirectoryName($Fixture.result_path)) 'checkout-passport.json'
    # Keep the engine's exact plan values: a PowerShell object round trip turns
    # timestamp strings into DateTime and writes them back in another form.
    $document = [System.Text.Json.JsonDocument]::Parse($preparedText.Text)
    try {
        $planText = $document.RootElement.GetProperty('data').GetProperty('plan').GetRawText()
    } finally { $document.Dispose() }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($planText)
    $stream = [IO.File]::Open($preparation, [IO.FileMode]::CreateNew)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
    $null = Read-Native @('local', 'apply', '--plan', $preparation, '--plan-digest', $prepared.plan_digest)
    Invoke-Control (Wait-Element $Process (Text 'shell.company') ([System.Windows.Automation.ControlType]::Hyperlink))
    Invoke-Control (Wait-Element $Process 'Read projects' ([System.Windows.Automation.ControlType]::Button))
    $null = Wait-Element $Process 'Installed shared project' $null
    Invoke-Control (Wait-Element $Process (Text 'corporate.reviewLocalCheckout') ([System.Windows.Automation.ControlType]::Button))
    Enter-Context $Process $Fixture.checkout_root 'checkoutPreview.checkoutDirectory' $false
    Enter-Context $Process $Fixture.git_executable 'checkoutPreview.gitExecutableOptional' $false
    Invoke-Control (Wait-Element $Process (Text 'checkoutPreview.previewCheckout') ([System.Windows.Automation.ControlType]::Button))
    $null = Wait-Element $Process (Text 'checkoutPreview.checkoutVerifiedForReview') $null
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 checkout_request')
    Invoke-Control (Wait-Element $Process (Text 'checkoutPreview.reviewLinkRequest') ([System.Windows.Automation.ControlType]::Button))
    Invoke-Control (Wait-Element $Process (Text 'checkoutPreview.exactCheckoutPlan') $null $true)
    $requestPlan = Read-PublicPlan $Process 'en' 'checkoutPreview.reviewCorporateCheckoutChange'
    $request = Assert-CheckoutIntent $requestPlan $Fixture $Corporate 'request'
    if ($request.Local -cne $local) { throw 'Checkout review changed its registered local project' }
    Confirm-ExactReview $Process 'checkoutPreview.iReviewedThisExactCheckoutPlanAndAuthorizeIts' 'checkoutPreview.applyReviewedCheckoutChange'
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 checkout_confirmation')
    Invoke-Control (Wait-Element $Process (Text 'checkoutPreview.reviewLinkConfirmation') ([System.Windows.Automation.ControlType]::Button))
    Invoke-Control (Wait-Element $Process (Text 'checkoutPreview.exactCheckoutPlan') $null $true)
    $confirmationPlan = Read-PublicPlan $Process 'en' 'checkoutPreview.reviewCorporateCheckoutChange'
    $confirmation = Assert-CheckoutIntent $confirmationPlan $Fixture $Corporate 'confirm' $request.Operation
    if ($confirmation.Local -cne $local -or $confirmation.Operation -ceq $request.Operation) {
        throw 'Checkout confirmation changed its original operation'
    }
    Confirm-ExactReview $Process 'checkoutPreview.iReviewedThisExactCheckoutPlanAndAuthorizeIts' 'checkoutPreview.applyReviewedCheckoutChange'
    $null = Wait-Element $Process (Text 'error.requestFailed') $null
    $unconfirmed = Read-Native @('corporate', 'project', 'link', 'show', '--operation', $confirmation.Operation)
    if ($unconfirmed.state -cne 'applying' -or $unconfirmed.plan_digest -cne $confirmationPlan.Digest) {
        throw 'Lost checkout reply did not retain the original pending confirmation'
    }
    return [pscustomobject]@{
        Request = $request.Operation; Confirmation = $confirmation.Operation
        ConfirmationDigest = $confirmationPlan.Digest; Local = $local
    }
}

function Resume-CorporateCheckout([System.Diagnostics.Process] $Process, $Fixture, $Corporate, $Pending) {
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 checkout_reconciliation')
    Invoke-Control (Wait-Element $Process (Text 'shell.activity') ([System.Windows.Automation.ControlType]::Hyperlink))
    Invoke-Control (Wait-Element $Process (Text 'checkoutOperations.readCheckoutHistory') ([System.Windows.Automation.ControlType]::Button))
    Invoke-Control (Wait-Element $Process ((Text 'checkoutOperations.inspect') + ' ' + $Pending.Confirmation) (
        [System.Windows.Automation.ControlType]::Button
    ))
    Confirm-ExactReview $Process 'checkoutOperations.iReviewedThisOriginalIntentAndAuthorizeOutcomeReconciliation' 'checkoutOperations.reconcileOriginalOutcome'
    $null = Wait-Element $Process (Text 'checkoutOperations.reviewOriginalLocalBinding') ([System.Windows.Automation.ControlType]::Button)
    $reconciled = Read-Native @('corporate', 'project', 'link', 'show', '--operation', $Pending.Confirmation)
    if ($reconciled.state -cne 'completed' -or $reconciled.operation_id -cne $Pending.Confirmation -or
        $reconciled.plan_digest -cne $Pending.ConfirmationDigest) {
        throw 'Checkout reconciliation replaced the original confirmation'
    }
    $root = Wait-Element $Process (Text 'checkoutOperations.registeredCheckoutForBinding') ([System.Windows.Automation.ControlType]::Edit)
    if ((Read-EditValue $root) -cne $Fixture.checkout_root) {
        throw 'Checkout recovery did not retain the original directory'
    }
    Enter-Context $Process $Fixture.git_executable 'checkoutOperations.trustedGitExecutableForCheckoutReviewOptional' $false
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 checkout_binding')
    Invoke-Control (Wait-Element $Process (Text 'checkoutOperations.reviewOriginalLocalBinding') ([System.Windows.Automation.ControlType]::Button))
    Invoke-Control (Wait-Element $Process (Text 'checkoutOperations.exactRetainedCheckoutNextPlan') $null $true)
    $plan = Read-PublicPlan $Process 'en' 'checkoutOperations.reviewRetainedCheckoutNextChange'
    $adoption = Assert-CheckoutIntent $plan $Fixture $Corporate 'adopt' $Pending.Request
    if ($adoption.Local -cne $Pending.Local -or $adoption.Operation -ceq $Pending.Request -or
        $adoption.Operation -ceq $Pending.Confirmation) {
        throw 'Checkout adoption replaced the original project or operation'
    }
    Confirm-ExactReview $Process 'checkoutOperations.iReviewedThisExactRetainedCheckoutChangeAndAuthorize' 'checkoutOperations.applyReviewedOriginalCheckoutChange'
    $null = Wait-Element $Process (Text 'checkoutOperations.originalCorporateProjectBindingReceiptSaved') $null
    $retained = Read-Native @('corporate', 'project', 'link', 'show', '--operation', $adoption.Operation)
    if ($retained.state -cne 'completed' -or $retained.plan_digest -cne $plan.Digest -or
        $retained.effect.link.state -cne 'linked' -or $retained.effect.link.link_id -isnot [string] -or
        !$retained.effect.link.link_id) {
        throw 'Installed checkout binding does not match its original receipt'
    }
    return [ordered]@{
        request_operation_id = $Pending.Request; confirmation_operation_id = $Pending.Confirmation
        adoption_operation_id = $adoption.Operation; context_id = $Corporate.Context
        local_project_id = $adoption.Local; link_id = $retained.effect.link.link_id
    }
}

function Test-PersonalJourney([System.Diagnostics.Process] $Process) {
    Invoke-Control (Wait-Element $Process (Text 'shell.connections') ([System.Windows.Automation.ControlType]::Hyperlink))
    $null = Wait-Element $Process (Text 'profiles.connectionsAndContexts') $null
    $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty, (Text 'shell.light')
    )
    $initialDark = $null -ne $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
    $script:contextTextReplacements = 0
    $first = New-ContextReview $Process 'Native personal one'
    $firstId = Assert-Review $first 'create' 'Native personal one'
    $locale = 'en'
    $combinations = 0
    foreach ($dark in @($false, $true)) {
        Set-Theme $Process $locale $dark
        foreach ($next in @($languageConfiguration.languages.Keys | Sort-Object)) {
            Select-Language $Process $locale $next
            $locale = $next
            Assert-Sidebar $Process $locale
            $current = Read-Review $Process $locale
            if ($current.Raw -cne $first.Raw -or $current.Digest -cne $first.Digest) {
                throw 'Appearance changes replaced the retained context plan'
            }
            $field = Wait-Element $Process (Text 'profiles.contextLabel' $locale) ([System.Windows.Automation.ControlType]::Edit)
            if ((Read-EditValue $field) -cne 'Native personal one') {
                throw 'Language change replaced entered context text'
            }
            $checkbox = Wait-Element $Process (Text 'profiles.iReviewedThisExactPlanAndAuthorizeThisLocal' $locale) (
                [System.Windows.Automation.ControlType]::CheckBox
            )
            if ($checkbox.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState -ne
                [System.Windows.Automation.ToggleState]::Off) {
                throw 'Appearance changes confirmed a context review'
            }
            $combinations++
        }
    }
    Select-Language $Process $locale 'en'
    Confirm-Review $Process
    $second = New-ContextReview $Process 'Native personal two'
    $secondId = Assert-Review $second 'create' 'Native personal two'
    if ($firstId -ceq $secondId) { throw 'Native contexts share an identity' }
    Confirm-Review $Process
    $discarded = New-ContextReview $Process 'Native dismissed context'
    $null = Assert-Review $discarded 'create' 'Native dismissed context'
    Invoke-Control (Wait-Element $Process (Text 'profiles.dismissReview') ([System.Windows.Automation.ControlType]::Button))
    $listed = Read-Native @('context', 'list')
    $ids = @($listed.contexts | ForEach-Object { $_.context.context_id })
    if ($ids.Count -ne 2 -or $firstId -cnotin $ids -or $secondId -cnotin $ids) {
        throw 'Dismissed context review changed native records'
    }
    if ($script:contextTextReplacements -ne 2) {
        throw 'Native context text replacement coverage differs'
    }
    Select-Context $Process 'Native personal one' $firstId
    Select-Context $Process 'Native personal two' $secondId
    Set-Theme $Process 'en' (!$initialDark)
    Select-Language $Process 'en' 'ar'
    return [pscustomobject]@{ Selected = $secondId; Dark = !$initialDark; Combinations = $combinations }
}

$corporateFixture = Read-CorporateFixture
$corporateStarted = $false
$version = Read-Native @('version')
if ($version.runtime -cne 'rust' -or $version.wire_schema_version -ne 1) {
    throw 'Installed CLI version contract differs'
}
$doctor = Read-Native @('doctor')
if (@($doctor.checks | Where-Object { $_.name -ceq 'local_identity' -and $_.state -ceq 'needs_user_action' }).Count -ne 1) {
    throw 'First-run Windows workspace is required'
}
$application = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../../apps/desktop/src-tauri/tauri.conf.json') | ConvertFrom-Json
$windowState = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData)) (
    Join-Path $application.identifier '.window-state.json'
)
if (Test-Path -LiteralPath $windowState) { throw 'First-run native window state is required' }
$process = Start-Process -FilePath $app -PassThru -RedirectStandardOutput (
    Join-Path $env:RUNNER_TEMP 'desktop-private-out.log'
) -RedirectStandardError (Join-Path $env:RUNNER_TEMP 'desktop-private-error.log')
try {
    Assert-NormalWorkArea $process 'initial'
    $initialWorkArea = [NativeDesktopInput]::WorkArea($process.MainWindowHandle)
    Show-Desktop $process
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
    [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 personal')
    $personal = Test-PersonalJourney $process
    if ($personal.Combinations -ne $languageConfiguration.languages.Count * 2) {
        throw 'Native appearance cases are incomplete'
    }
    Close-Desktop $process
    Set-OversizedNormalState $windowState $initialWorkArea
    $process = Start-Process -FilePath $app -PassThru -RedirectStandardOutput (
    Join-Path $env:RUNNER_TEMP 'desktop-private-out.log'
) -RedirectStandardError (Join-Path $env:RUNNER_TEMP 'desktop-private-error.log')
    Assert-NormalWorkArea $process 'restored'
    Show-Desktop $process
    $null = Wait-Element $process (Text 'language.label' 'ar') ([System.Windows.Automation.ControlType]::ComboBox)
    $themeKey = if ($personal.Dark) { 'shell.light' } else { 'shell.dark' }
    $null = Wait-Element $process (Text $themeKey 'ar') ([System.Windows.Automation.ControlType]::Button)
    Assert-Sidebar $process 'ar'
    Assert-SelectedContext $process $personal.Selected
    Select-Language $process 'ar' 'en'
    $link = Wait-Element $process (Text 'shell.connections') ([System.Windows.Automation.ControlType]::Hyperlink)
    $tabSteps = Focus-KeyboardLink $process $link
    Assert-KeyboardFocus $process $link
    Write-Host ([ordered]@{
        native_navigation_focus = 'observed_by_keyboard'
        traversal_steps = $tabSteps
        native_focus_is_root = [NativeDesktopInput]::KeyboardFocusIsRoot($process.MainWindowHandle)
    } | ConvertTo-Json -Compress)
    $injected = [NativeDesktopInput]::Enter()
    Write-Host ('Native navigation keyboard events accepted: ' + $injected)
    $null = Wait-Element $process (Text 'profiles.connectionsAndContexts') $null
    $null = Wait-Element $process ('Native personal two' + (Text 'profiles.selectedView')) $null
    if (@((Read-Native @('context', 'list')).contexts).Count -ne 2) {
        throw 'Restart lost native context records'
    }
    Open-Settings $process
    $null = Wait-Element $process 'Initialized' $null
    if ((Read-Native @('device', 'show') | ConvertTo-Json -Depth 10 -Compress) -cne $identity) {
        throw 'Installed device identity changed after restart'
    }
    if ($null -ne $corporateFixture) {
        $corporateStarted = $true
        $corporate = Test-CorporateJourney $process $corporateFixture $identity
        Close-Desktop $process
        [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 restart')
        $process = Start-Process -FilePath $app -PassThru -RedirectStandardOutput (
            Join-Path $env:RUNNER_TEMP 'desktop-private-out.log'
        ) -RedirectStandardError (Join-Path $env:RUNNER_TEMP 'desktop-private-error.log')
        Show-Desktop $process
        $null = Wait-Element $process (Text 'language.label') ([System.Windows.Automation.ControlType]::ComboBox)
        Assert-SelectedContext $process $corporate.Context
        Invoke-Control (Wait-Element $process (Text 'shell.connections') ([System.Windows.Automation.ControlType]::Hyperlink))
        $null = Wait-Element $process ('Native corporate context' + (Text 'profiles.selectedView')) $null
        if (@((Read-Native @('context', 'list')).contexts).Count -ne 3) {
            throw 'Restart lost coexisting personal and corporate contexts'
        }
        Assert-CorporateSession $corporateFixture $corporate.Connection
        if ((Read-Native @('device', 'show') | ConvertTo-Json -Depth 10 -Compress) -cne $identity) {
            throw 'Corporate restart changed the original device identity'
        }
        $pendingCheckout = Start-CorporateCheckout $process $corporateFixture $corporate
        Close-Desktop $process
        [Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 checkout_restart')
        $process = Start-Process -FilePath $app -PassThru -RedirectStandardOutput (
            Join-Path $env:RUNNER_TEMP 'desktop-private-out.log'
        ) -RedirectStandardError (Join-Path $env:RUNNER_TEMP 'desktop-private-error.log')
        Show-Desktop $process
        $null = Wait-Element $process (Text 'language.label') ([System.Windows.Automation.ControlType]::ComboBox)
        Assert-SelectedContext $process $corporate.Context
        $checkout = Resume-CorporateCheckout $process $corporateFixture $corporate $pendingCheckout
        Assert-CorporateSession $corporateFixture $corporate.Connection
        if ((Read-Native @('device', 'show') | ConvertTo-Json -Depth 10 -Compress) -cne $identity) {
            throw 'Checkout recovery changed the original enrolled identity'
        }
    }
    Close-Desktop $process
    if ($null -ne $corporateFixture) {
        $controls = [ordered]@{}
        foreach ($key in @(
            'installed_personal_journey_retained', 'connection_exact_plan_and_confirmation',
            'original_pending_confirmation_after_navigation', 'device_bound_account_session',
            'corporate_context_exact_plan_and_confirmation', 'personal_and_corporate_contexts_coexist',
            'context_view_selection_explicit', 'corporate_context_survives_restart',
            'original_device_survives_restart', 'original_account_and_origin_preserved'
        )) { $controls[$key] = $true }
        $checkoutControls = [ordered]@{}
        foreach ($key in @(
            'committed_checkout_preview', 'request_exact_plan_and_confirmation',
            'confirmation_exact_plan_and_confirmation', 'committed_reply_lost',
            'original_operation_reconciled_after_restart', 'binding_exact_plan_and_confirmation',
            'original_link_and_device_preserved', 'unowned_checkout_bytes_and_identity_preserved'
        )) { $checkoutControls[$key] = $true }
        $result = [ordered]@{
            schema_version = 2; source_sha = $Source; controls = $controls
            checkout_controls = $checkoutControls; checkout = $checkout
            enrolled_device_id = $corporate.Device; desktop_process_stopped = $process.HasExited
        } | ConvertTo-Json -Depth 5
        $stream = [IO.File]::Open($corporateFixture.result_path, [IO.FileMode]::CreateNew)
        try {
            $bytes = [Text.Encoding]::UTF8.GetBytes($result)
            $stream.Write($bytes, 0, $bytes.Length)
        } finally { $stream.Dispose() }
    }
} catch {
    if (!$corporateStarted) { Save-NativeFailureImage $process }
    throw
} finally {
    if (!$process.HasExited) { Stop-Process -Id $process.Id }
}

[Console]::Out.WriteLine('AI_STP_NATIVE_DESKTOP_STAGE_V1 complete')
[ordered]@{
    schema_version = 2
    source_sha = $Source
    installer_sha256 = $msi[0].sha256
    app_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash.ToLowerInvariant()
    cli_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $cli).Hash.ToLowerInvariant()
    cli_version = $version.cli_version
    installed_personal_workspace_restart = $true
    theme_locale_observations = $personal.Combinations
    native_text_selection_replacements = $script:contextTextReplacements
    native_text_input_api = 'SendInput_UNICODE_SCANCODE'
    native_combo_input_api = 'SendInput_POINTER_UIA_SELECTION'
    personal_controls = [ordered]@{
        native_vault_initialization = $true
        two_native_offline_contexts = $true
        exact_context_plan_and_explicit_confirmation = $true
        dismissed_review_has_no_effect = $true
        native_keyboard_text_and_navigation = $true
        theme_locale_changes_preserve_fields_and_review = $true
        rtl_sidebar_mirrors = $true
        selected_context_survives_restart = $true
        theme_and_locale_survive_restart = $true
        device_identity_survives_restart = $true
    }
    normal_window_controls = [ordered]@{
        first_normal_window_within_work_area = $true
        oversized_normal_state_restored_within_work_area = $true
        context_and_preferences_survive_geometry_recovery = $true
    }
    corporate_acceptance = $false
    release_authorized = $false
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding ASCII

# Exercise an exact candidate MSI using the Windows accessibility tree.
param(
    [Parameter(Mandatory)][string] $Bundle,
    [Parameter(Mandatory)][string] $Source,
    [Parameter(Mandatory)][string] $Output
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
trap {
    [Console]::Error.WriteLine('Native owner call site: ' + $_.ScriptStackTrace)
    throw
}
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'A disposable hosted Windows runner is required'
}
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 is required' }
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

function Wait-Element([System.Diagnostics.Process] $Process, [string] $Name, $ControlType, [bool] $AllowDisabled = $false) {
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
            if ($null -ne $element -and ($AllowDisabled -or $element.Current.IsEnabled)) { return $element }
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


$catalogRoot = Join-Path $PSScriptRoot '../../apps/desktop/src/locales'
$languageConfiguration = Get-Content -Raw -LiteralPath (Join-Path $catalogRoot '../localization.json') | ConvertFrom-Json -AsHashtable
$catalogs = @{}
foreach ($locale in $languageConfiguration.languages.Keys) {
    $catalogs[$locale] = Get-Content -Raw -LiteralPath (Join-Path $catalogRoot ($locale + '.json')) | ConvertFrom-Json -AsHashtable
}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NativeDesktopInput {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(IntPtr window);
}
'@

function Text([string] $Key, [string] $Locale = 'en') {
    if (!$catalogs.ContainsKey($Locale) -or !$catalogs[$Locale].ContainsKey($Key)) {
        throw 'A required packaged message is unavailable'
    }
    return [string] $catalogs[$Locale][$Key]
}

function Wait-Observation([System.Diagnostics.Process] $Process, [string] $Label, [scriptblock] $Observe) {
    $deadline = [Diagnostics.Stopwatch]::StartNew()
    while ($deadline.Elapsed.TotalSeconds -lt 45) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "Installed Desktop exited before $Label" }
        $value = & $Observe
        if ($null -ne $value -and $value -ne $false) { return $value }
        Start-Sleep -Milliseconds 200
    }
    throw "Timed out waiting for $Label"
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

function Enter-Context([System.Diagnostics.Process] $Process, [string] $Label) {
    if ($Label -cnotmatch '^[A-Za-z0-9 ]{1,120}$') { throw 'Unexpected keyboard fixture text' }
    $field = Wait-Element $Process (Text 'profiles.contextLabel') ([System.Windows.Automation.ControlType]::Edit)
    Focus-Control $Process $field
    [System.Windows.Forms.SendKeys]::SendWait('^a')
    [System.Windows.Forms.SendKeys]::SendWait($Label)
    $null = Wait-Observation $Process 'entered context label' ({
        $pattern = $field.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        if ($pattern.Current.Value -ceq $Label) { return $true }
        return $null
    }.GetNewClosure())
}

function Read-Review([System.Diagnostics.Process] $Process, [string] $Locale = 'en') {
    $region = Wait-Element $Process (Text 'profiles.reviewNativeProfilePlan' $Locale) $null $true
    return Wait-Observation $Process 'exact public context plan' ({
        $nodes = $region.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition
        )
        if ($nodes.Count -gt 2500) { throw 'Native review tree exceeds its observation bound' }
        $raw = $null
        $change = $null
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
                if ($document -is [System.Collections.IDictionary] -and $document.Contains('change') -and
                    $document.change -is [System.Collections.IDictionary] -and $document.change.Contains('context')) {
                    $change = $document.change
                    $raw = $value
                }
            }
        }
        if ($null -ne $raw -and $null -ne $digest) {
            return [pscustomobject]@{ Raw = $raw; Digest = $digest; Context = $change.context; Action = $change.action }
        }
        return $null
    }.GetNewClosure())
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

function Confirm-Review([System.Diagnostics.Process] $Process) {
    $confirmation = Wait-Element $Process (Text 'profiles.iReviewedThisExactPlanAndAuthorizeThisLocal') (
        [System.Windows.Automation.ControlType]::CheckBox
    )
    $toggle = $confirmation.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
    if ($toggle.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::Off) {
        throw 'Context review was already confirmed'
    }
    $apply = Wait-Element $Process (Text 'profiles.applyReviewedChange') (
        [System.Windows.Automation.ControlType]::Button
    ) $true
    if ($apply.Current.IsEnabled) { throw 'Unconfirmed context review was applicable' }
    $toggle.Toggle()
    Invoke-Control (Wait-Element $Process (Text 'profiles.applyReviewedChange') ([System.Windows.Automation.ControlType]::Button))
    $null = Wait-Observation $Process 'context review completion' ({
        $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
        $condition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty, (Text 'profiles.reviewNativeProfilePlan')
        )
        if ($null -eq $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)) { return $true }
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

function Select-Language([System.Diagnostics.Process] $Process, [string] $Previous, [string] $Next) {
    $selector = Wait-Element $Process (Text 'language.label' $Previous) ([System.Windows.Automation.ControlType]::ComboBox)
    $name = [string] $languageConfiguration.languages[$Next].name
    if ($Next -ceq 'kk') { $name += ' · ' + $languageConfiguration.languages[$Next].shortName }
    $selection = $selector.GetCurrentPattern([System.Windows.Automation.SelectionPattern]::Pattern).Current.GetSelection()
    if ($selection.Count -ne 1) { throw 'Native language selection is ambiguous' }
    if ($selection[0].Current.Name -cne $name) {
        $expand = $selector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
        $expand.Expand()
        $option = Wait-Observation $Process 'packaged native language option' ({
            $condition = [System.Windows.Automation.PropertyCondition]::new(
                [System.Windows.Automation.AutomationElement]::NameProperty, $name
            )
            return $selector.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
        }.GetNewClosure())
        $option.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        if ($expand.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Expanded) {
            $expand.Collapse()
        }
    }
    $null = Wait-Element $Process (Text 'language.label' $Next) ([System.Windows.Automation.ControlType]::ComboBox)
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
    $null = Wait-Element $Process (Text 'language.label' $Locale) ([System.Windows.Automation.ControlType]::ComboBox)
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

function Test-PersonalJourney([System.Diagnostics.Process] $Process) {
    Invoke-Control (Wait-Element $Process (Text 'shell.connections') ([System.Windows.Automation.ControlType]::Hyperlink))
    $null = Wait-Element $Process (Text 'profiles.connectionsAndContexts') $null
    $window = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::NameProperty, (Text 'shell.light')
    )
    $initialDark = $null -ne $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
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
            if ($field.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value -cne 'Native personal one') {
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
    Select-Context $Process 'Native personal one' $firstId
    Select-Context $Process 'Native personal two' $secondId
    Set-Theme $Process 'en' (!$initialDark)
    Select-Language $Process 'en' 'ar'
    return [pscustomobject]@{ Selected = $secondId; Dark = !$initialDark; Combinations = $combinations }
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
    $personal = Test-PersonalJourney $process
    if ($personal.Combinations -ne $languageConfiguration.languages.Count * 2) {
        throw 'Native appearance cases are incomplete'
    }
    Close-Desktop $process
    $process = Start-Process -FilePath $app -PassThru
    $null = Wait-Element $process (Text 'language.label' 'ar') ([System.Windows.Automation.ControlType]::ComboBox)
    $themeKey = if ($personal.Dark) { 'shell.light' } else { 'shell.dark' }
    $null = Wait-Element $process (Text $themeKey 'ar') ([System.Windows.Automation.ControlType]::Button)
    Assert-Sidebar $process 'ar'
    Assert-SelectedContext $process $personal.Selected
    Select-Language $process 'ar' 'en'
    $link = Wait-Element $process (Text 'shell.connections') ([System.Windows.Automation.ControlType]::Hyperlink)
    Focus-Control $process $link
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
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
    Close-Desktop $process
} finally {
    if (!$process.HasExited) { Stop-Process -Id $process.Id }
}

[ordered]@{
    schema_version = 2
    source_sha = $Source
    installer_sha256 = $msi[0].sha256
    app_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $app).Hash.ToLowerInvariant()
    cli_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $cli).Hash.ToLowerInvariant()
    cli_version = $version.cli_version
    installed_personal_workspace_restart = $true
    theme_locale_observations = $personal.Combinations
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
    corporate_acceptance = $false
    release_authorized = $false
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding ASCII

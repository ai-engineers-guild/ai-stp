Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms

foreach ($path in @(& git ls-files -- '*.ps1')) {
    $tokens = $null
    $syntaxErrors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path (Get-Location) $path), [ref] $tokens, [ref] $syntaxErrors
    )
    if ($syntaxErrors.Count -gt 0) {
        foreach ($problem in $syntaxErrors) {
            Write-Error ($path + ':' + $problem.Extent.StartLineNumber + ': ' + $problem.ErrorId) -ErrorAction Continue
        }
        exit 1
    }
}
if ($LASTEXITCODE -ne 0) { throw 'Tracked PowerShell sources could not be enumerated' }

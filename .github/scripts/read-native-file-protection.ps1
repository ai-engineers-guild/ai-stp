param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') {
    throw 'Native Windows file protection requires Windows'
}
$item = Get-Item -LiteralPath $Path -Force
$sections = [Security.AccessControl.AccessControlSections]::Access -bor
    [Security.AccessControl.AccessControlSections]::Owner -bor
    [Security.AccessControl.AccessControlSections]::Group
$descriptor = (Get-Acl -LiteralPath $Path).GetSecurityDescriptorSddlForm($sections)
[ordered]@{
    attributes = [int]$item.Attributes
    descriptor = $descriptor
} | ConvertTo-Json -Compress

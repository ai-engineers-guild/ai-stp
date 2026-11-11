# Read only the directories owned by this synthetic installation fixture.
$ErrorActionPreference = 'Stop'
$paths = $env:AI_STP_FIXTURE_DIRECTORIES | ConvertFrom-Json
$results = foreach ($entry in $paths.PSObject.Properties) {
    try {
        $item = Get-Item -LiteralPath $entry.Value -Force
        $acl = Get-Acl -LiteralPath $entry.Value
        [ordered]@{
            role = $entry.Name
            attributes = [int]$item.Attributes
            sddl = $acl.Sddl
        }
    } catch {
        [ordered]@{ role = $entry.Name; error = $_.CategoryInfo.Category.ToString() }
    }
}
$results | ConvertTo-Json -Depth 4 -Compress

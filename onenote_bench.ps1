
$ErrorActionPreference = 'Stop'
$timer = [System.Diagnostics.Stopwatch]::StartNew()

# Create OneNote COM object once
$onenote = New-Object -ComObject 'OneNote.Application'
Write-Host ('COM object created in {0:F3}s' -f $timer.Elapsed.TotalSeconds)

# Get full hierarchy (scope=4 = hsPages)
[xml]$hier = $null
$onenote.GetHierarchy('', 4, [ref]$hier)
Write-Host ('Hierarchy loaded in {0:F3}s' -f $timer.Elapsed.TotalSeconds)

# Get page IDs
$ns = @{one='http://schemas.microsoft.com/office/onenote/2013/onenote'}
$pages = Select-Xml -Xml $hier -XPath '//one:Page' -Namespace $ns | Select-Object -First 10
Write-Host ('Found {0} pages (taking first 10)' -f ($pages | Measure-Object).Count)

# Loop through first 10 pages
$pageTimes = @()
foreach ($page in $pages) {
    $pageID = $page.Node.ID
    $pageName = $page.Node.name
    $t0 = [System.Diagnostics.Stopwatch]::StartNew()
    [string]$content = $null
    $onenote.GetPageContent($pageID, [ref]$content, 0, 2)  # piBasic=0
    $t0.Stop()
    $pageTimes += $t0.Elapsed.TotalMilliseconds
    Write-Host ('  Page ({0}): {1:F0}ms, {2:N0} chars' -f $pageName.Substring(0,[Math]::Min(30,$pageName.Length)), $t0.Elapsed.TotalMilliseconds, $content.Length)
}

$avg = ($pageTimes | Measure-Object -Average).Average
$total = ($pageTimes | Measure-Object -Sum).Sum
Write-Host ''
Write-Host ('Total for 10 pages: {0:F2}s' -f ($total/1000))
Write-Host ('Average per page: {0:F1}ms' -f $avg)
Write-Host ('Pages/second: {0:F2}' -f (10000 / $total))

$timer.Stop()
Write-Host ('Script total time: {0:F3}s' -f $timer.Elapsed.TotalSeconds)
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($onenote) | Out-Null

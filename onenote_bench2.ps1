
$ErrorActionPreference = 'Stop'
$timer = [System.Diagnostics.Stopwatch]::StartNew()

$onenote = New-Object -ComObject 'OneNote.Application'
[xml]$hier = $null
$onenote.GetHierarchy('', 4, [ref]$hier)
Write-Host ('Setup in {0:F3}s' -f $timer.Elapsed.TotalSeconds)

$ns = @{one='http://schemas.microsoft.com/office/onenote/2013/onenote'}
$allPages = Select-Xml -Xml $hier -XPath '//one:Page' -Namespace $ns
$pages = $allPages | Select-Object -Skip 50 -First 10

$pageTimes = @()
foreach ($page in $pages) {
    $pageID = $page.Node.ID
    $pageName = $page.Node.name
    $t0 = [System.Diagnostics.Stopwatch]::StartNew()
    [string]$content = $null
    $onenote.GetPageContent($pageID, [ref]$content, 0, 2)
    $t0.Stop()
    $pageTimes += $t0.Elapsed.TotalMilliseconds
    Write-Host ('  Page ({0}): {1:F0}ms, {2:N0} chars' -f $pageName.Substring(0,[Math]::Min(30,$pageName.Length)), $t0.Elapsed.TotalMilliseconds, $content.Length)
}

$avg = ($pageTimes | Measure-Object -Average).Average
$total = ($pageTimes | Measure-Object -Sum).Sum
Write-Host ('Total: {0:F2}s, Avg: {1:F1}ms, Rate: {2:F2} pages/s' -f ($total/1000), $avg, (10000/$total))
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($onenote) | Out-Null

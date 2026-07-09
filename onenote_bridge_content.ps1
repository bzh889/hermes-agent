
$onenote = New-Object -ComObject 'OneNote.Application'
[xml]$hier = $null
$onenote.GetHierarchy('', 4, [ref]$hier)
Write-Output 'READY'
[Console]::Out.Flush()

while ($true) {
    $line = [Console]::In.ReadLine()
    if ($line -eq 'QUIT') { break }
    [string]$content = $null
    try {
        $onenote.GetPageContent($line, [ref]$content, 0, 2)
        # Send content length + content (base64 for safety with special chars)
        $b64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($content))
        Write-Output ('OK {0}' -f $b64.Length)
        Write-Output $b64
    } catch {
        Write-Output ('ERR {0}' -f $_.Exception.Message)
    }
    [Console]::Out.Flush()
}
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($onenote) | Out-Null

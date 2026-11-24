param([string]$WavePath)
$ErrorActionPreference = 'Stop'
$speaker = New-Object -ComObject SAPI.SpVoice
$voices = $speaker.GetVoices()
$chosen = $null
foreach ($voice in $voices) {
    if ($voice.GetAttribute('Language') -match '(^|;)419(;|$)') { $chosen = $voice; break }
}
if ($null -eq $chosen) { throw 'Russian SAPI voice is unavailable' }
$speaker.Voice = $chosen
if ($WavePath) {
    $stream = New-Object -ComObject SAPI.SpFileStream
    $stream.Format.Type = 22 # 22.05 kHz, 16 bit, mono PCM
    $stream.Open($WavePath, 3)
    $speaker.AudioOutputStream = $stream
}
try { [void]$speaker.Speak($env:JARVIS_SPEECH) }
finally { if ($WavePath) { $stream.Close() } }

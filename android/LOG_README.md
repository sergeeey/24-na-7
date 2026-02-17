# Просмотр логов Reflexio в PowerShell

**adb не в PATH?** Используй полный путь:
```powershell
& "C:\Users\serge\AppData\Local\Android\Sdk\platform-tools\adb.exe" logcat -d
```

В PowerShell нет команд `head` и `tail`. Используй эквиваленты:

## Последние 200 строк лога
```powershell
Get-Content "d:\24 na 7\.cursor\debug.log" -Tail 200
```

## Первые 100 строк
```powershell
Get-Content "d:\24 na 7\.cursor\debug.log" -TotalCount 100
```

## Поиск по ключевым словам (первые 100 совпадений)
```powershell
Select-String -Path "d:\24 na 7\.cursor\debug.log" -Pattern "RFLX_DBG|AndroidRuntime|FATAL|MainActivity|AudioRecordingService|Exception|Error" | Select-Object -First 100
```

## Только Reflexio и краши
```powershell
Select-String -Path "d:\24 na 7\.cursor\debug.log" -Pattern "reflexio|FATAL EXCEPTION|AndroidRuntime" | Select-Object -First 80
```

## Сохранить отфильтрованный лог в файл
```powershell
Select-String -Path "d:\24 na 7\.cursor\debug.log" -Pattern "reflexio|FATAL|Exception|MainActivity|AudioRecording" | Set-Content "d:\24 na 7\.cursor\filtered_debug.log"
Get-Content "d:\24 na 7\.cursor\filtered_debug.log"
```

## Сбор свежих логов (очистить → запусти приложение → сохранить)
```powershell
adb logcat -c
# Запусти Reflexio на устройстве, воспроизведи проблему
Read-Host "Нажми Enter после воспроизведения"
adb logcat -d > "d:\24 na 7\.cursor\debug.log"
Get-Content "d:\24 na 7\.cursor\debug.log" -Tail 150
```

## Сохранить логи в проект (с подключённого устройства)
Логи пишутся в `android/logs/` (папка в .gitignore). Укажи свой серийник вместо `53031FDAP000ZA`, если нужно:
```powershell
$adb = "C:\Users\serge\AppData\Local\Android\Sdk\platform-tools\adb.exe"
$outDir = "d:\24 na 7\android\logs"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force }
$ts = Get-Date -Format "yyyy-MM-dd_HH-mm"
& $adb -s 53031FDAP000ZA logcat -d > "$outDir\logcat_full_$ts.txt"
& $adb -s 53031FDAP000ZA logcat -d -t 2000 | Select-String -Pattern "AudioRecordingService|MainActivity|RFLX_DBG|IngestWebSocket|RecordingApp|Segment|VAD|Failed|Error|Exception|Service started|speech frames" | Set-Content "$outDir\logcat_reflexio_$ts.txt" -Encoding UTF8
Get-ChildItem $outDir -Filter "*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 4 Name, Length, LastWriteTime
```

## Только логи Reflexio (последние 150 строк)
Подставь свой путь к adb, если нужно:
```powershell
& "C:\Users\serge\AppData\Local\Android\Sdk\platform-tools\adb.exe" logcat -d -t 800 2>$null | Select-String -Pattern "AudioRecordingService|MainActivity|RFLX_DBG|IngestWebSocket|RecordingApp" | Select-Object -Last 150
```

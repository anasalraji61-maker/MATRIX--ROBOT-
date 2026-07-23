' Launches Matrix Robot without showing a PowerShell/CMD window.
' Double-click this file (or the Desktop shortcut) to start the app.

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

bat = fso.GetParentFolderName(WScript.ScriptFullName) & "\start-matrix-robot.bat"

' 0 = hidden window
shell.Run """" & bat & """", 0, False

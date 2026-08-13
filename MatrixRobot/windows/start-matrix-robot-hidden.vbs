' Starts Matrix Robot completely hidden (no PowerShell windows).
' Use the Desktop shortcut created by install-desktop-shortcut.bat

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
bat = fso.GetParentFolderName(WScript.ScriptFullName) & "\start-matrix-robot.bat"
shell.Run """" & bat & """", 0, False

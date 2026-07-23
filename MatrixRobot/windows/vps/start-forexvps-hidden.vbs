' Starts ForexVPS Matrix Robot stack hidden.
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
bat = fso.GetParentFolderName(WScript.ScriptFullName) & "\start-forexvps.bat"
shell.Run """" & bat & """", 0, False

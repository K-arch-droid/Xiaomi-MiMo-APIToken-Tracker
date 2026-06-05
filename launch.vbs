Set objShell = CreateObject("WScript.Shell")
objShell.Run "pythonw """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\token_tracker.py""", 0, False

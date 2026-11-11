Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
root = fs.GetParentFolderName(folder)
python = root & "\AnnaData-Backend-main\.venv\Scripts\pythonw.exe"
If Not fs.FileExists(python) Then
    MsgBox "The backend Python environment is missing. See local_mandi/README.md.", 16, "AnnaData"
Else
    shell.Run """" & python & """ """ & folder & "\app.py"" --autostart", 1, False
End If

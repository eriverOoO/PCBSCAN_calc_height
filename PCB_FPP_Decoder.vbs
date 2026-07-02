Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
app = root & "\dist\PCB_FPP_Decoder\PCB_FPP_Decoder.exe"

If Not fso.FileExists(app) Then
  MsgBox "PCB FPP Decoder app was not found:" & vbCrLf & app & vbCrLf & vbCrLf & "Run build.bat first.", vbCritical, "PCB FPP Decoder"
  WScript.Quit 1
End If

shell.Run """" & app & """", 1, False

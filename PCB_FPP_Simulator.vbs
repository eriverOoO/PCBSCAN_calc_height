Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
app = root & "\dist\PCB_FPP_Simulator_Fixed\PCB_FPP_Simulator_Fixed.exe"

If Not fso.FileExists(app) Then
  MsgBox "PCB FPP Simulator app was not found:" & vbCrLf & app & vbCrLf & vbCrLf & "Run build.bat first.", vbCritical, "PCB FPP Simulator"
  WScript.Quit 1
End If

shell.Run """" & app & """", 1, False

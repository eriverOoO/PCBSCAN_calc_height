Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$SimulatorExe = Join-Path $Root "dist\PCB_FPP_Simulator_Fixed\PCB_FPP_Simulator_Fixed.exe"

function Quote-Arg {
    param([string]$Value)
    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

function Add-Label {
    param($Parent, [string]$Text, [int]$X, [int]$Y)
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.Location = New-Object System.Drawing.Point($X, $Y)
    $label.Size = New-Object System.Drawing.Size(120, 22)
    $Parent.Controls.Add($label)
    return $label
}

function Add-TextBox {
    param($Parent, [string]$Text, [int]$X, [int]$Y, [int]$Width = 120)
    $box = New-Object System.Windows.Forms.TextBox
    $box.Text = $Text
    $box.Location = New-Object System.Drawing.Point($X, $Y)
    $box.Size = New-Object System.Drawing.Size($Width, 22)
    $Parent.Controls.Add($box)
    return $box
}

function Add-Checkbox {
    param($Parent, [string]$Text, [int]$X, [int]$Y, [bool]$Checked = $false)
    $check = New-Object System.Windows.Forms.CheckBox
    $check.Text = $Text
    $check.Location = New-Object System.Drawing.Point($X, $Y)
    $check.Size = New-Object System.Drawing.Size(150, 24)
    $check.Checked = $Checked
    $Parent.Controls.Add($check)
    return $check
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "PCB FPP Simulator"
$form.Size = New-Object System.Drawing.Size(760, 650)
$form.MinimumSize = New-Object System.Drawing.Size(760, 650)
$form.StartPosition = "CenterScreen"

$font = New-Object System.Drawing.Font("Segoe UI", 9)
$form.Font = $font

$outputGroup = New-Object System.Windows.Forms.GroupBox
$outputGroup.Text = "Output"
$outputGroup.Location = New-Object System.Drawing.Point(12, 10)
$outputGroup.Size = New-Object System.Drawing.Size(720, 70)
$form.Controls.Add($outputGroup)

Add-Label $outputGroup "Output root" 12 28 | Out-Null
$outputBox = Add-TextBox $outputGroup (Join-Path $Root "simulations\virtual_pcb_gui") 130 26 470
$browseButton = New-Object System.Windows.Forms.Button
$browseButton.Text = "Browse"
$browseButton.Location = New-Object System.Drawing.Point(610, 24)
$browseButton.Size = New-Object System.Drawing.Size(90, 26)
$outputGroup.Controls.Add($browseButton)

$sceneGroup = New-Object System.Windows.Forms.GroupBox
$sceneGroup.Text = "Synthetic Scene"
$sceneGroup.Location = New-Object System.Drawing.Point(12, 90)
$sceneGroup.Size = New-Object System.Drawing.Size(350, 220)
$form.Controls.Add($sceneGroup)

Add-Label $sceneGroup "Width" 12 30 | Out-Null
$widthBox = Add-TextBox $sceneGroup "320" 150 28
Add-Label $sceneGroup "Height" 12 60 | Out-Null
$heightBox = Add-TextBox $sceneGroup "200" 150 58
Add-Label $sceneGroup "Stripe width px" 12 90 | Out-Null
$stripeBox = Add-TextBox $sceneGroup "5.0" 150 88
Add-Label $sceneGroup "Height scale" 12 120 | Out-Null
$heightScaleBox = Add-TextBox $sceneGroup "1.0" 150 118
Add-Label $sceneGroup "Noise sigma" 12 150 | Out-Null
$noiseBox = Add-TextBox $sceneGroup "0.0" 150 148
Add-Label $sceneGroup "Blur sigma" 12 180 | Out-Null
$blurBox = Add-TextBox $sceneGroup "0.0" 150 178

$decodeGroup = New-Object System.Windows.Forms.GroupBox
$decodeGroup.Text = "Decoder / Options"
$decodeGroup.Location = New-Object System.Drawing.Point(382, 90)
$decodeGroup.Size = New-Object System.Drawing.Size(350, 220)
$form.Controls.Add($decodeGroup)

Add-Label $decodeGroup "Random seed" 12 30 | Out-Null
$seedBox = Add-TextBox $decodeGroup "7" 150 28
Add-Label $decodeGroup "Median filter" 12 60 | Out-Null
$medianBox = Add-TextBox $decodeGroup "0" 150 58
Add-Label $decodeGroup "Max 3D points" 12 90 | Out-Null
$pointsBox = Add-TextBox $decodeGroup "300000" 150 88

$invertedCheck = Add-Checkbox $decodeGroup "Inverted Gray" 12 122 $true
$defectsCheck = Add-Checkbox $decodeGroup "Defects" 175 122 $false
$boundaryCheck = Add-Checkbox $decodeGroup "Boundary correction" 12 152 $false
$detrendCheck = Add-Checkbox $decodeGroup "Detrend" 175 152 $false

$actions = New-Object System.Windows.Forms.Panel
$actions.Location = New-Object System.Drawing.Point(12, 320)
$actions.Size = New-Object System.Drawing.Size(720, 38)
$form.Controls.Add($actions)

$runButton = New-Object System.Windows.Forms.Button
$runButton.Text = "Run simulation"
$runButton.Location = New-Object System.Drawing.Point(0, 0)
$runButton.Size = New-Object System.Drawing.Size(520, 32)
$actions.Controls.Add($runButton)

$openButton = New-Object System.Windows.Forms.Button
$openButton.Text = "Open output"
$openButton.Location = New-Object System.Drawing.Point(536, 0)
$openButton.Size = New-Object System.Drawing.Size(180, 32)
$actions.Controls.Add($openButton)

$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Multiline = $true
$logBox.ScrollBars = "Vertical"
$logBox.ReadOnly = $true
$logBox.Location = New-Object System.Drawing.Point(12, 370)
$logBox.Size = New-Object System.Drawing.Size(720, 230)
$logBox.Anchor = "Left,Top,Right,Bottom"
$form.Controls.Add($logBox)

$browseButton.Add_Click({
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Choose simulation output folder"
    $dialog.SelectedPath = $outputBox.Text
    if ($dialog.ShowDialog($form) -eq [System.Windows.Forms.DialogResult]::OK) {
        $outputBox.Text = $dialog.SelectedPath
    }
})

$openButton.Add_Click({
    if (-not [string]::IsNullOrWhiteSpace($outputBox.Text)) {
        New-Item -ItemType Directory -Force -Path $outputBox.Text | Out-Null
        Start-Process explorer.exe -ArgumentList (Quote-Arg $outputBox.Text)
    }
})

$runButton.Add_Click({
    if (-not (Test-Path $SimulatorExe)) {
        [System.Windows.Forms.MessageBox]::Show(
            $form,
            "Simulator executable was not found:`n$SimulatorExe`n`nRun build_simulator.bat first.",
            "PCB FPP Simulator",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        return
    }

    $args = @(
        "--output", $outputBox.Text,
        "--width", $widthBox.Text,
        "--height", $heightBox.Text,
        "--stripe-width-px", $stripeBox.Text,
        "--height-scale", $heightScaleBox.Text,
        "--noise-sigma", $noiseBox.Text,
        "--blur-sigma", $blurBox.Text,
        "--seed", $seedBox.Text,
        "--median-filter", $medianBox.Text,
        "--max-point-cloud-points", $pointsBox.Text
    )
    if (-not $invertedCheck.Checked) { $args += "--no-inverted-gray" }
    if ($defectsCheck.Checked) { $args += "--add-defects" }
    if ($boundaryCheck.Checked) { $args += "--boundary-correction" }
    if ($detrendCheck.Checked) { $args += "--detrend" }

    $logBox.Clear()
    $logBox.AppendText("Running simulation...`r`n")
    $runButton.Enabled = $false

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $SimulatorExe
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.Arguments = ($args | ForEach-Object { Quote-Arg ([string]$_) }) -join " "

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    $process.EnableRaisingEvents = $true

    $appendLine = {
        param([string]$Line)
        if ($null -ne $Line) {
            $form.BeginInvoke([Action]{
                $logBox.AppendText($Line + [Environment]::NewLine)
                $logBox.SelectionStart = $logBox.TextLength
                $logBox.ScrollToCaret()
            }) | Out-Null
        }
    }

    $process.add_OutputDataReceived({
        param($sender, $eventArgs)
        & $appendLine $eventArgs.Data
    })
    $process.add_ErrorDataReceived({
        param($sender, $eventArgs)
        & $appendLine $eventArgs.Data
    })
    $process.add_Exited({
        $exitCode = $process.ExitCode
        $form.BeginInvoke([Action]{
            $logBox.AppendText("`r`nProcess exited with code $exitCode`r`n")
            $runButton.Enabled = $true
        }) | Out-Null
        $process.Dispose()
    })

    try {
        [void]$process.Start()
        $process.BeginOutputReadLine()
        $process.BeginErrorReadLine()
    } catch {
        $runButton.Enabled = $true
        [System.Windows.Forms.MessageBox]::Show(
            $form,
            $_.Exception.Message,
            "Run failed",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
})

[void]$form.ShowDialog()

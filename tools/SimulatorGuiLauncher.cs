using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace PcbFppSimulatorGui
{
    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--self-test")
            {
                Console.WriteLine(FindProjectRoot());
                Console.WriteLine(FindSimulatorExe() ?? "");
                return FindSimulatorExe() == null ? 1 : 0;
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SimulatorForm());
            return 0;
        }

        internal static string FindProjectRoot()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            DirectoryInfo current = new DirectoryInfo(baseDir);
            for (int i = 0; i < 5 && current != null; i++)
            {
                if (Directory.Exists(Path.Combine(current.FullName, "dist")) ||
                    File.Exists(Path.Combine(current.FullName, "requirements.txt")))
                {
                    return current.FullName;
                }
                current = current.Parent;
            }
            DirectoryInfo parent = Directory.GetParent(baseDir);
            if (parent != null && parent.Parent != null)
            {
                return parent.Parent.FullName;
            }
            return baseDir;
        }

        internal static string FindSimulatorExe()
        {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string root = FindProjectRoot();
            string[] candidates = new string[]
            {
                Path.Combine(root, "dist", "PCB_FPP_Simulator_Fixed", "PCB_FPP_Simulator_Fixed.exe"),
                Path.Combine(root, "dist", "PCB_FPP_Simulator_CLI", "PCB_FPP_Simulator_CLI.exe"),
                Path.Combine(baseDir, "..", "PCB_FPP_Simulator_Fixed", "PCB_FPP_Simulator_Fixed.exe"),
                Path.Combine(baseDir, "PCB_FPP_Simulator_Fixed.exe")
            };

            foreach (string candidate in candidates)
            {
                string fullPath = Path.GetFullPath(candidate);
                if (File.Exists(fullPath))
                {
                    return fullPath;
                }
            }
            return null;
        }
    }

    internal sealed class SimulatorForm : Form
    {
        private readonly string root;
        private readonly string simulatorExe;
        private readonly TextBox outputBox;
        private readonly TextBox widthBox;
        private readonly TextBox heightBox;
        private readonly TextBox stripeBox;
        private readonly TextBox heightScaleBox;
        private readonly TextBox noiseBox;
        private readonly TextBox blurBox;
        private readonly TextBox seedBox;
        private readonly TextBox medianBox;
        private readonly TextBox pointsBox;
        private readonly CheckBox invertedCheck;
        private readonly CheckBox defectsCheck;
        private readonly CheckBox boundaryCheck;
        private readonly CheckBox detrendCheck;
        private readonly TextBox logBox;
        private readonly Button runButton;
        private readonly Button openButton;

        internal SimulatorForm()
        {
            root = Program.FindProjectRoot();
            simulatorExe = Program.FindSimulatorExe();

            Text = "PCB FPP Simulator";
            MinimumSize = new Size(760, 650);
            Size = new Size(760, 650);
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 9.0f);

            GroupBox outputGroup = AddGroup("Output", 12, 10, 720, 70);
            AddLabel(outputGroup, "Output root", 12, 28);
            outputBox = AddTextBox(outputGroup, Path.Combine(root, "simulations", "virtual_pcb_gui"), 130, 26, 470);
            Button browseButton = AddButton(outputGroup, "Browse", 610, 24, 90, 26);
            browseButton.Click += BrowseButton_Click;

            GroupBox sceneGroup = AddGroup("Synthetic Scene", 12, 90, 350, 220);
            AddLabel(sceneGroup, "Width", 12, 30);
            widthBox = AddTextBox(sceneGroup, "320", 150, 28, 120);
            AddLabel(sceneGroup, "Height", 12, 60);
            heightBox = AddTextBox(sceneGroup, "200", 150, 58, 120);
            AddLabel(sceneGroup, "Stripe width px", 12, 90);
            stripeBox = AddTextBox(sceneGroup, "5.0", 150, 88, 120);
            AddLabel(sceneGroup, "Height scale", 12, 120);
            heightScaleBox = AddTextBox(sceneGroup, "1.0", 150, 118, 120);
            AddLabel(sceneGroup, "Noise sigma", 12, 150);
            noiseBox = AddTextBox(sceneGroup, "0.0", 150, 148, 120);
            AddLabel(sceneGroup, "Blur sigma", 12, 180);
            blurBox = AddTextBox(sceneGroup, "0.0", 150, 178, 120);

            GroupBox decodeGroup = AddGroup("Decoder / Options", 382, 90, 350, 220);
            AddLabel(decodeGroup, "Random seed", 12, 30);
            seedBox = AddTextBox(decodeGroup, "7", 150, 28, 120);
            AddLabel(decodeGroup, "Median filter", 12, 60);
            medianBox = AddTextBox(decodeGroup, "0", 150, 58, 120);
            AddLabel(decodeGroup, "Max 3D points", 12, 90);
            pointsBox = AddTextBox(decodeGroup, "300000", 150, 88, 120);
            invertedCheck = AddCheckBox(decodeGroup, "Inverted Gray", 12, 122, true);
            defectsCheck = AddCheckBox(decodeGroup, "Defects", 175, 122, false);
            boundaryCheck = AddCheckBox(decodeGroup, "Boundary correction", 12, 152, false);
            detrendCheck = AddCheckBox(decodeGroup, "Detrend", 175, 152, false);

            Panel actions = new Panel();
            actions.Location = new Point(12, 320);
            actions.Size = new Size(720, 38);
            Controls.Add(actions);

            runButton = AddButton(actions, "Run simulation", 0, 0, 520, 32);
            runButton.Click += RunButton_Click;
            openButton = AddButton(actions, "Open output", 536, 0, 180, 32);
            openButton.Click += OpenButton_Click;

            logBox = new TextBox();
            logBox.Multiline = true;
            logBox.ScrollBars = ScrollBars.Vertical;
            logBox.ReadOnly = true;
            logBox.Location = new Point(12, 370);
            logBox.Size = new Size(720, 230);
            logBox.Anchor = AnchorStyles.Left | AnchorStyles.Top | AnchorStyles.Right | AnchorStyles.Bottom;
            Controls.Add(logBox);
        }

        private GroupBox AddGroup(string text, int x, int y, int width, int height)
        {
            GroupBox group = new GroupBox();
            group.Text = text;
            group.Location = new Point(x, y);
            group.Size = new Size(width, height);
            Controls.Add(group);
            return group;
        }

        private static void AddLabel(Control parent, string text, int x, int y)
        {
            Label label = new Label();
            label.Text = text;
            label.Location = new Point(x, y);
            label.Size = new Size(125, 22);
            parent.Controls.Add(label);
        }

        private static TextBox AddTextBox(Control parent, string text, int x, int y, int width)
        {
            TextBox box = new TextBox();
            box.Text = text;
            box.Location = new Point(x, y);
            box.Size = new Size(width, 22);
            parent.Controls.Add(box);
            return box;
        }

        private static CheckBox AddCheckBox(Control parent, string text, int x, int y, bool isChecked)
        {
            CheckBox check = new CheckBox();
            check.Text = text;
            check.Location = new Point(x, y);
            check.Size = new Size(155, 24);
            check.Checked = isChecked;
            parent.Controls.Add(check);
            return check;
        }

        private static Button AddButton(Control parent, string text, int x, int y, int width, int height)
        {
            Button button = new Button();
            button.Text = text;
            button.Location = new Point(x, y);
            button.Size = new Size(width, height);
            parent.Controls.Add(button);
            return button;
        }

        private void BrowseButton_Click(object sender, EventArgs e)
        {
            using (FolderBrowserDialog dialog = new FolderBrowserDialog())
            {
                dialog.Description = "Choose simulation output folder";
                dialog.SelectedPath = outputBox.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    outputBox.Text = dialog.SelectedPath;
                }
            }
        }

        private void OpenButton_Click(object sender, EventArgs e)
        {
            Directory.CreateDirectory(outputBox.Text);
            Process.Start("explorer.exe", Quote(outputBox.Text));
        }

        private void RunButton_Click(object sender, EventArgs e)
        {
            if (simulatorExe == null)
            {
                MessageBox.Show(this, "Simulator backend executable was not found. Run build_simulator.bat first.", "PCB FPP Simulator", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            List<string> args = new List<string>
            {
                "--output", outputBox.Text,
                "--width", widthBox.Text,
                "--height", heightBox.Text,
                "--stripe-width-px", stripeBox.Text,
                "--height-scale", heightScaleBox.Text,
                "--noise-sigma", noiseBox.Text,
                "--blur-sigma", blurBox.Text,
                "--seed", seedBox.Text,
                "--median-filter", medianBox.Text,
                "--max-point-cloud-points", pointsBox.Text
            };
            if (!invertedCheck.Checked) args.Add("--no-inverted-gray");
            if (defectsCheck.Checked) args.Add("--add-defects");
            if (boundaryCheck.Checked) args.Add("--boundary-correction");
            if (detrendCheck.Checked) args.Add("--detrend");

            logBox.Clear();
            AppendLog("Running simulation...");
            runButton.Enabled = false;

            Process process = new Process();
            process.StartInfo.FileName = simulatorExe;
            process.StartInfo.WorkingDirectory = root;
            process.StartInfo.UseShellExecute = false;
            process.StartInfo.RedirectStandardOutput = true;
            process.StartInfo.RedirectStandardError = true;
            process.StartInfo.CreateNoWindow = true;
            process.StartInfo.Arguments = JoinArguments(args);
            process.EnableRaisingEvents = true;
            process.OutputDataReceived += delegate(object outputSender, DataReceivedEventArgs outputArgs)
            {
                if (outputArgs.Data != null) AppendLog(outputArgs.Data);
            };
            process.ErrorDataReceived += delegate(object errorSender, DataReceivedEventArgs errorArgs)
            {
                if (errorArgs.Data != null) AppendLog(errorArgs.Data);
            };
            process.Exited += delegate
            {
                int exitCode = process.ExitCode;
                process.Dispose();
                BeginInvoke((Action)(() =>
                {
                    AppendLog("");
                    AppendLog("Process exited with code " + exitCode);
                    runButton.Enabled = true;
                }));
            };

            try
            {
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
            }
            catch (Exception ex)
            {
                runButton.Enabled = true;
                MessageBox.Show(this, ex.Message, "Run failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void AppendLog(string text)
        {
            if (InvokeRequired)
            {
                BeginInvoke((Action)(() => AppendLog(text)));
                return;
            }
            logBox.AppendText(text + Environment.NewLine);
            logBox.SelectionStart = logBox.TextLength;
            logBox.ScrollToCaret();
        }

        private static string JoinArguments(IEnumerable<string> args)
        {
            List<string> quoted = new List<string>();
            foreach (string arg in args)
            {
                quoted.Add(Quote(arg));
            }
            return string.Join(" ", quoted.ToArray());
        }

        private static string Quote(string value)
        {
            if (value == null) return "\"\"";
            if (value.IndexOfAny(new char[] { ' ', '\t', '"' }) < 0) return value;
            return "\"" + value.Replace("\"", "\\\"") + "\"";
        }
    }
}

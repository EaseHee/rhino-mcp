using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using Rhino;
using Rhino.Commands;

namespace RhinoMcp.Commands
{
    /// <summary>
    /// "_McpInstall" command: install the rhino3dm-mcp PyPI package and
    /// register it inside Claude Desktop's config without requiring the
    /// user to leave Rhino. Rhino discovers this class via assembly
    /// scanning of the loaded .rhp plugin.
    /// </summary>
    public class McpInstallCommand : Command
    {
        private const string PypiDistribution = "rhino3dm-mcp";
        private const string ConsoleScript = "rhino-mcp";

        public McpInstallCommand()
        {
            Instance = this;
        }

        public static McpInstallCommand? Instance { get; private set; }

        public override string EnglishName => "McpInstall";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            RhinoApp.WriteLine("[rhino-mcp] Starting Claude Desktop install...");

            // Mode is left as `auto`: the MCP server auto-detects the bridge
            // on every launch, so Claude Desktop attaches to a live Rhino
            // when one is running and falls back to standalone (rhino3dm)
            // when Rhino is closed. No user choice required.

            var launcher = LauncherResolver.Resolve();
            if (launcher == null)
            {
                RhinoApp.WriteLine(
                    "[rhino-mcp] Could not find uvx, pipx, pip, or python on PATH.");
                RhinoApp.WriteLine(
                    "[rhino-mcp] Install uv first: https://docs.astral.sh/uv/getting-started/installation/");
                RhinoApp.WriteLine(
                    "[rhino-mcp] Or run from a terminal: pip install rhino3dm-mcp && rhino-mcp install");
                return Result.Failure;
            }

            RhinoApp.WriteLine($"[rhino-mcp] Using launcher: {launcher.Description}");

            var args = launcher.BuildInstallArgs();
            var (exitCode, stdout, stderr) = ProcessRunner.Run(launcher.Executable, args);

            foreach (var line in SplitLines(stdout))
                RhinoApp.WriteLine($"[rhino-mcp] {line}");
            foreach (var line in SplitLines(stderr))
                RhinoApp.WriteLine($"[rhino-mcp] {line}");

            if (exitCode == 0)
            {
                RhinoApp.WriteLine("[rhino-mcp] Done. Restart Claude Desktop to pick up the change.");
                return Result.Success;
            }

            RhinoApp.WriteLine($"[rhino-mcp] Install failed (exit code {exitCode}).");
            return Result.Failure;
        }

        private static IEnumerable<string> SplitLines(string text)
        {
            if (string.IsNullOrEmpty(text))
                yield break;
            using var reader = new StringReader(text);
            string? line;
            while ((line = reader.ReadLine()) != null)
            {
                if (line.Length > 0)
                    yield return line;
            }
        }
    }

    internal sealed class Launcher
    {
        public string Executable { get; }
        public LauncherKind Kind { get; }
        public string Description { get; }

        public Launcher(string executable, LauncherKind kind, string description)
        {
            Executable = executable;
            Kind = kind;
            Description = description;
        }

        public List<string> BuildInstallArgs()
        {
            var args = new List<string>();
            switch (Kind)
            {
                case LauncherKind.Uvx:
                    args.Add("--from");
                    args.Add(McpInstallConstants.PypiDistribution);
                    args.Add(McpInstallConstants.ConsoleScript);
                    args.Add("install");
                    break;
                case LauncherKind.ConsoleScript:
                    args.Add("install");
                    break;
                case LauncherKind.Python:
                    args.Add("-m");
                    args.Add("rhino_mcp.server");
                    args.Add("install");
                    break;
            }
            // `install.py` defaults to --mode auto --transport stdio; passing
            // them explicitly would only shadow the same values. --force lets
            // the command be re-run after the user moved Rhino to a new
            // location or upgraded Python.
            args.Add("--force");
            return args;
        }
    }

    internal enum LauncherKind
    {
        Uvx,
        ConsoleScript,
        Python,
    }

    internal static class McpInstallConstants
    {
        public const string PypiDistribution = "rhino3dm-mcp";
        public const string ConsoleScript = "rhino-mcp";
    }

    internal static class LauncherResolver
    {
        private static readonly string[] MacFallbackDirs =
        {
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
        };

        public static Launcher? Resolve()
        {
            var uvx = FindOnPath("uvx");
            if (uvx != null)
                return new Launcher(uvx, LauncherKind.Uvx, $"uvx ({uvx})");

            var script = FindOnPath(McpInstallConstants.ConsoleScript);
            if (script != null)
                return new Launcher(script, LauncherKind.ConsoleScript, $"installed rhino-mcp ({script})");

            var python = FindOnPath("python3") ?? FindOnPath("python");
            if (python != null)
                return new Launcher(python, LauncherKind.Python, $"python -m rhino_mcp.server ({python})");

            return null;
        }

        public static string? FindOnPath(string executable)
        {
            var pathEnv = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
            var dirs = new List<string>(pathEnv.Split(Path.PathSeparator));

            if (Environment.OSVersion.Platform == PlatformID.Unix ||
                Environment.OSVersion.Platform == PlatformID.MacOSX ||
                OperatingSystem.IsMacOS())
            {
                var home = Environment.GetEnvironmentVariable("HOME");
                if (!string.IsNullOrEmpty(home))
                {
                    dirs.Add(Path.Combine(home, ".local", "bin"));
                    dirs.Add(Path.Combine(home, ".cargo", "bin"));
                }
                dirs.AddRange(MacFallbackDirs);
            }

            var suffixes = OperatingSystem.IsWindows()
                ? new[] { ".exe", ".cmd", ".bat", "" }
                : new[] { "" };

            foreach (var dir in dirs)
            {
                if (string.IsNullOrEmpty(dir)) continue;
                foreach (var sfx in suffixes)
                {
                    var candidate = Path.Combine(dir, executable + sfx);
                    if (File.Exists(candidate))
                        return candidate;
                }
            }
            return null;
        }
    }

    internal static class ProcessRunner
    {
        public static (int ExitCode, string Stdout, string Stderr) Run(string executable, IList<string> args)
        {
            var psi = new ProcessStartInfo
            {
                FileName = executable,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };
            foreach (var a in args)
                psi.ArgumentList.Add(a);

            var stdoutBuf = new StringBuilder();
            var stderrBuf = new StringBuilder();
            using var proc = new Process { StartInfo = psi };
            proc.OutputDataReceived += (_, e) => { if (e.Data != null) stdoutBuf.AppendLine(e.Data); };
            proc.ErrorDataReceived += (_, e) => { if (e.Data != null) stderrBuf.AppendLine(e.Data); };
            proc.Start();
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            proc.WaitForExit();
            return (proc.ExitCode, stdoutBuf.ToString(), stderrBuf.ToString());
        }
    }
}

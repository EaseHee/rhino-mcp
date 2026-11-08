using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Commands;
using Rhino.Input;
using Rhino.Input.Custom;
using RhinoMcp.Setup;

namespace RhinoMcp.Commands
{
    /// <summary>
    /// "_McpInstall" command: register (or remove) the rhino3dm-mcp server in
    /// the configs of the selected MCP clients (Claude Desktop, Claude Code,
    /// Codex, Antigravity) without leaving Rhino. The client choice is made
    /// with command-line toggles; Enter accepts the current selection, so the
    /// scripted form <c>-_McpInstall</c> runs with the detected defaults.
    /// </summary>
    public class McpInstallCommand : Command
    {
        public McpInstallCommand()
        {
            Instance = this;
        }

        public static McpInstallCommand? Instance { get; private set; }

        public override string EnglishName => "McpInstall";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            // Mode is left as `auto`: the MCP server auto-detects the bridge
            // on every launch, so a client attaches to a live Rhino when one
            // is running and falls back to standalone (rhino3dm) otherwise.

            var candidates = LauncherResolver.Candidates();
            if (candidates.Count == 0)
            {
                RhinoApp.WriteLine(
                    "[rhino-mcp] Could not find uvx, rhino-mcp, or python on PATH.");

                if (UvAutoInstaller.OfferInstall())
                {
                    RhinoApp.WriteLine("[rhino-mcp] Re-checking for uv...");
                    candidates = LauncherResolver.Candidates();
                }

                if (candidates.Count == 0)
                {
                    RhinoApp.WriteLine(
                        "[rhino-mcp] Still cannot find a launcher. If uv was just installed, "
                        + "restart Rhino so the updated PATH is picked up, then run _McpInstall again.");
                    RhinoApp.WriteLine(
                        "[rhino-mcp] Manual install: https://docs.astral.sh/uv/getting-started/installation/");
                    RhinoApp.WriteLine(
                        "[rhino-mcp] Or run from a terminal: pip install rhino3dm-mcp && rhino-mcp install");
                    return Result.Failure;
                }
            }

            var rejected = new List<string>();
            var launcher = LauncherResolver.ResolveCompatible(candidates, rejected);
            foreach (var line in rejected)
                RhinoApp.WriteLine($"[rhino-mcp] Skipped {line}.");
            if (launcher == null)
            {
                var floor = McpInstallConstants.MinServerVersion;
                RhinoApp.WriteLine(
                    $"[rhino-mcp] No launcher provides rhino-mcp {floor} or newer, which this plug-in needs.");
                RhinoApp.WriteLine(
                    $"[rhino-mcp] Until {McpInstallConstants.PypiDistribution} {floor} is on PyPI, install the server "
                    + "from a local rhino-mcp checkout and run _McpInstall again:");
                RhinoApp.WriteLine(
                    $"[rhino-mcp]   uv tool install --force --from <path-to-rhino-mcp> {McpInstallConstants.PypiDistribution}");
                return Result.Failure;
            }

            RhinoApp.WriteLine($"[rhino-mcp] Using launcher: {launcher.Description}");

            var clients = McpClientInfo.Query(launcher);
            var selection = PromptForClients(clients, out var uninstall);
            if (selection == null)
                return Result.Cancel;
            if (selection.Count == 0)
            {
                RhinoApp.WriteLine("[rhino-mcp] No client selected; nothing to do.");
                return Result.Nothing;
            }

            var labels = string.Join(", ", selection.Select(c => c.Label));
            RhinoApp.WriteLine(uninstall
                ? $"[rhino-mcp] Removing rhino-mcp from: {labels}"
                : $"[rhino-mcp] Registering rhino-mcp in: {labels}");

            var args = launcher.BuildArgs(uninstall ? "uninstall" : "install");
            if (!uninstall)
            {
                // --force lets the command be re-run after Rhino or Python moved;
                // --launcher pins the registered command so a uvx child never
                // writes its temporary uv-cache interpreter path.
                args.Add("--force");
                args.Add("--launcher");
                args.Add(launcher.KindArgument);
            }
            foreach (var client in selection)
            {
                args.Add("--client");
                args.Add(client.Name);
            }

            var (exitCode, stdout, stderr) = ProcessRunner.Run(launcher.Executable, args);
            ProcessRunner.WriteOutput(stdout, stderr);

            if (exitCode == 0)
            {
                RhinoApp.WriteLine($"[rhino-mcp] Done. Restart {labels} to pick up the change.");
                return Result.Success;
            }

            if (McpInstallConstants.LooksLikeOldInstaller(stderr))
                McpInstallConstants.WriteUpgradeHint(launcher);
            RhinoApp.WriteLine(uninstall
                ? $"[rhino-mcp] Uninstall failed (exit code {exitCode})."
                : $"[rhino-mcp] Install failed (exit code {exitCode}).");
            return Result.Failure;
        }

        /// <summary>
        /// Shows the client toggles. Returns null on cancel, otherwise the
        /// enabled clients (possibly empty).
        /// </summary>
        private static List<McpClientInfo>? PromptForClients(
            IReadOnlyList<McpClientInfo> clients, out bool uninstall)
        {
            uninstall = false;
            var toggles = clients
                .Select(c => new OptionToggle(c.InitiallyOn, "Off", "On"))
                .ToArray();
            var uninstallToggle = new OptionToggle(false, "No", "Yes");

            var go = new GetOption();
            go.SetCommandPrompt("Select MCP clients (Enter to accept)");
            go.AcceptNothing(true);

            while (true)
            {
                go.ClearCommandOptions();
                for (var i = 0; i < clients.Count; i++)
                    go.AddOptionToggle(clients[i].OptionName, ref toggles[i]);
                var allIndex = go.AddOption("All");
                go.AddOptionToggle("Uninstall", ref uninstallToggle);

                var res = go.Get();
                if (res == GetResult.Nothing)
                    break;
                if (res == GetResult.Option)
                {
                    if (go.OptionIndex() == allIndex)
                    {
                        foreach (var t in toggles)
                            t.CurrentValue = true;
                    }
                    continue;
                }
                return null;
            }

            uninstall = uninstallToggle.CurrentValue;
            var selected = new List<McpClientInfo>();
            for (var i = 0; i < clients.Count; i++)
            {
                if (toggles[i].CurrentValue)
                    selected.Add(clients[i]);
            }
            return selected;
        }
    }

    /// <summary>One MCP client as reported by <c>install --list-clients --json</c>.</summary>
    internal sealed class McpClientInfo
    {
        public string Name { get; }
        public string Label { get; }
        public string OptionName { get; }
        public bool InitiallyOn { get; set; }

        private McpClientInfo(string name, string label, string optionName)
        {
            Name = name;
            Label = label;
            OptionName = optionName;
        }

        private static List<McpClientInfo> Defaults() => new()
        {
            new McpClientInfo("claude-desktop", "Claude Desktop", "ClaudeDesktop"),
            new McpClientInfo("claude-code", "Claude Code", "ClaudeCode"),
            new McpClientInfo("codex", "Codex", "Codex"),
            new McpClientInfo("antigravity", "Antigravity", "Antigravity"),
        };

        /// <summary>
        /// Fixed client list with initial toggles taken from the child's
        /// detection state; falls back to Claude Desktop only on failure.
        /// </summary>
        public static List<McpClientInfo> Query(Launcher launcher)
        {
            var clients = Defaults();
            var args = launcher.BuildArgs("install");
            args.Add("--list-clients");
            args.Add("--json");

            JArray? rows = null;
            try
            {
                var (exitCode, stdout, stderr) = ProcessRunner.Run(launcher.Executable, args);
                if (exitCode != 0 && McpInstallConstants.LooksLikeOldInstaller(stderr))
                    McpInstallConstants.WriteUpgradeHint(launcher);
                if (exitCode == 0)
                {
                    var jsonLine = ProcessRunner.SplitLines(stdout)
                        .LastOrDefault(l => l.TrimStart().StartsWith("[", StringComparison.Ordinal));
                    if (jsonLine != null)
                        rows = JArray.Parse(jsonLine);
                }
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[rhino-mcp] Client detection failed ({ex.Message}).");
            }

            if (rows != null)
            {
                foreach (var row in rows.OfType<JObject>())
                {
                    var name = (string?)row["name"];
                    var match = clients.FirstOrDefault(c => c.Name == name);
                    if (match == null)
                        continue;
                    // A row with a config error still means the client is present.
                    var hasError = !string.IsNullOrEmpty(row["error"]?.ToString());
                    match.InitiallyOn = hasError
                        || (row["detected"]?.Type == JTokenType.Boolean && row.Value<bool>("detected"))
                        || (row["installed"]?.Type == JTokenType.Boolean && row.Value<bool>("installed"));
                }
            }
            else
            {
                RhinoApp.WriteLine("[rhino-mcp] Could not list MCP clients; defaulting to Claude Desktop.");
            }

            if (!clients.Any(c => c.InitiallyOn))
                clients[0].InitiallyOn = true;
            return clients;
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

        /// <summary>Value for the child's <c>--launcher</c> flag.</summary>
        public string KindArgument => Kind switch
        {
            LauncherKind.Uvx => "uvx",
            LauncherKind.ConsoleScript => "rhino-mcp",
            _ => "python",
        };

        /// <summary>Launcher prefix followed by the given sub-command.</summary>
        public List<string> BuildArgs(string subcommand)
        {
            var args = new List<string>();
            switch (Kind)
            {
                case LauncherKind.Uvx:
                    // A version floor makes uvx skip a cached env holding an older
                    // installer that lacks --client / --list-clients.
                    args.Add("--from");
                    args.Add($"{McpInstallConstants.PypiDistribution}>={McpInstallConstants.MinServerVersion}");
                    args.Add(McpInstallConstants.ConsoleScript);
                    break;
                case LauncherKind.ConsoleScript:
                    break;
                case LauncherKind.Python:
                    args.Add("-m");
                    args.Add("rhino_mcp.server");
                    break;
            }
            args.Add(subcommand);
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

        /// <summary>Oldest server whose installer understands this command's flags (the plug-in's own version).</summary>
        public static string MinServerVersion =>
            typeof(McpInstallConstants).Assembly.GetName().Version?.ToString(3) ?? "0.7.0";

        public static Version MinServerVersionParsed =>
            Version.TryParse(MinServerVersion, out var v) ? v : new Version(0, 7, 0);

        /// <summary>Parse "rhino-mcp X.Y.Z" from <c>--version</c> output.</summary>
        public static Version? ParseServerVersion(string stdout)
        {
            foreach (var line in ProcessRunner.SplitLines(stdout).Reverse())
            {
                var match = System.Text.RegularExpressions.Regex.Match(line, @"rhino-mcp\s+(\d+\.\d+\.\d+)");
                if (match.Success && Version.TryParse(match.Groups[1].Value, out var v))
                    return v;
            }
            return null;
        }

        /// <summary>True when uv could not resolve the requested version floor.</summary>
        public static bool LooksUnsatisfiable(string stderr) =>
            stderr.Contains("No solution found", StringComparison.Ordinal)
            || stderr.Contains("unsatisfiable", StringComparison.Ordinal);

        /// <summary>True when argparse rejected our flags, i.e. the server package predates them.</summary>
        public static bool LooksLikeOldInstaller(string stderr) =>
            stderr.Contains("unrecognized arguments", StringComparison.Ordinal)
            || stderr.Contains("invalid choice", StringComparison.Ordinal);

        public static void WriteUpgradeHint(Launcher launcher)
        {
            RhinoApp.WriteLine(
                $"[rhino-mcp] The rhino-mcp server reached via {launcher.Description} is older than "
                + $"{MinServerVersion}. Upgrade it (e.g. `uv tool upgrade rhino3dm-mcp` or "
                + $"`pip install -U rhino3dm-mcp`) and run _McpInstall again.");
        }
    }

    internal static class LauncherResolver
    {
        private static readonly string[] MacFallbackDirs =
        {
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
        };

        /// <summary>Launchers found on this machine, in preference order (uvx, console script, python).</summary>
        public static List<Launcher> Candidates()
        {
            var found = new List<Launcher>();
            var uvx = FindOnPath("uvx");
            if (uvx != null)
                found.Add(new Launcher(uvx, LauncherKind.Uvx, $"uvx ({uvx})"));

            // Every match is a candidate: a stale script early on PATH must not hide a current one in ~/.local/bin.
            foreach (var script in FindAllOnPath(McpInstallConstants.ConsoleScript))
                found.Add(new Launcher(script, LauncherKind.ConsoleScript, $"installed rhino-mcp ({script})"));

            foreach (var python in FindAllOnPath("python3").Concat(FindAllOnPath("python")))
                found.Add(new Launcher(python, LauncherKind.Python, $"python -m rhino_mcp.server ({python})"));

            return found;
        }

        /// <summary>
        /// First candidate whose server is at least <see cref="McpInstallConstants.MinServerVersion"/>.
        /// A uvx candidate fails the probe when PyPI has no such release yet, so
        /// a local install (console script or python) is used instead of a
        /// server that would not understand this command's flags.
        /// </summary>
        public static Launcher? ResolveCompatible(IEnumerable<Launcher> candidates, List<string> rejected)
        {
            var floor = McpInstallConstants.MinServerVersionParsed;
            foreach (var launcher in candidates)
            {
                var (exitCode, stdout, stderr) = ProcessRunner.Run(launcher.Executable, launcher.BuildArgs("--version"));
                var version = exitCode == 0 ? McpInstallConstants.ParseServerVersion(stdout) : null;
                if (version != null && version >= floor)
                    return launcher;
                var reason = version != null
                    ? $"server {version.ToString(3)} is older than {floor.ToString(3)}"
                    : McpInstallConstants.LooksUnsatisfiable(stderr)
                        ? $"no {McpInstallConstants.PypiDistribution}>={floor.ToString(3)} on PyPI yet"
                        : $"server not runnable (exit code {exitCode})";
                rejected.Add($"{launcher.Description}: {reason}");
            }
            return null;
        }

        public static string? FindOnPath(string executable) => FindAllOnPath(executable).FirstOrDefault();

        /// <summary>Every distinct match for <paramref name="executable"/>, PATH first, then well-known dirs.</summary>
        public static List<string> FindAllOnPath(string executable)
        {
            var matches = new List<string>();
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
                    if (File.Exists(candidate) && !matches.Contains(candidate, StringComparer.Ordinal))
                        matches.Add(candidate);
                }
            }
            return matches;
        }
    }

    internal static class ProcessRunner
    {
        // Wall-clock cap on a single child-process invocation. Configurable
        // via RHINO_MCP_INSTALL_TIMEOUT_MS so a slow network or a paused
        // installer cannot freeze the Rhino UI thread indefinitely.
        private const int DefaultTimeoutMs = 180_000;

        private static int TimeoutMs
        {
            get
            {
                var raw = Environment.GetEnvironmentVariable("RHINO_MCP_INSTALL_TIMEOUT_MS");
                if (!string.IsNullOrEmpty(raw) && int.TryParse(raw, out var v) && v > 0)
                    return v;
                return DefaultTimeoutMs;
            }
        }

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
            var timeoutMs = TimeoutMs;
            if (!proc.WaitForExit(timeoutMs))
            {
                try { proc.Kill(entireProcessTree: true); }
                catch { /* best-effort */ }
                stderrBuf.AppendLine($"[rhino-mcp] process timed out after {timeoutMs} ms; killed.");
                // Drain remaining async output that might have been buffered
                // before the kill landed.
                try { proc.WaitForExit(2_000); } catch { /* best-effort */ }
                return (-1, stdoutBuf.ToString(), stderrBuf.ToString());
            }
            return (proc.ExitCode, stdoutBuf.ToString(), stderrBuf.ToString());
        }

        /// <summary>Non-empty lines of a captured output buffer.</summary>
        public static IEnumerable<string> SplitLines(string? text)
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

        /// <summary>Echo captured stdout then stderr to the Rhino command line.</summary>
        public static void WriteOutput(string? stdout, string? stderr)
        {
            foreach (var line in SplitLines(stdout))
                RhinoApp.WriteLine($"[rhino-mcp] {line}");
            foreach (var line in SplitLines(stderr))
                RhinoApp.WriteLine($"[rhino-mcp] {line}");
        }
    }
}

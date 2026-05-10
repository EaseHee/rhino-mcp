using System;
using System.Collections.Generic;
using System.IO;
using Rhino;
using Rhino.UI;
using RhinoMcp.Commands;

namespace RhinoMcp.Setup
{
    /// <summary>
    /// Offers to install uv (Astral's Python package launcher) when
    /// <c>_McpInstall</c> cannot find any usable launcher on PATH. The
    /// install runs the platform's official one-line installer; the
    /// user must confirm via a Rhino dialog before anything is
    /// downloaded.  Returns <c>true</c> only when uv was newly installed
    /// in this invocation, so the caller can re-resolve the launcher.
    /// </summary>
    internal static class UvAutoInstaller
    {
        private const string InstallerUrlPosix = "https://astral.sh/uv/install.sh";
        private const string InstallerUrlWindows = "https://astral.sh/uv/install.ps1";

        public static bool OfferInstall()
        {
            var url = OperatingSystem.IsWindows() ? InstallerUrlWindows : InstallerUrlPosix;
            var prompt = string.Join('\n',
                "uv (Python package launcher) was not found on PATH.",
                "",
                "Install uv automatically?",
                "Source: " + url,
                "(official Astral installer)",
                "",
                "After install, _McpInstall will continue automatically.");

            ShowMessageResult answer;
            try
            {
                answer = Dialogs.ShowMessage(
                    prompt,
                    "rhino-mcp setup",
                    ShowMessageButton.YesNo,
                    ShowMessageIcon.Question);
            }
            catch (Exception ex)
            {
                // Headless / non-UI sessions (e.g. _-RunCommand from a script
                // file): fall back to a console-only prompt-by-default policy.
                RhinoApp.WriteLine($"[rhino-mcp] Could not show install dialog ({ex.Message}). Skipping auto-install.");
                return false;
            }

            if (answer != ShowMessageResult.Yes)
            {
                RhinoApp.WriteLine("[rhino-mcp] uv install declined by user.");
                return false;
            }

            RhinoApp.WriteLine($"[rhino-mcp] Downloading uv from {url} ...");

            string executable;
            List<string> args;
            if (OperatingSystem.IsWindows())
            {
                executable = "powershell.exe";
                args = new List<string>
                {
                    "-ExecutionPolicy", "Bypass",
                    "-NoProfile",
                    "-Command",
                    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
                    + "irm " + InstallerUrlWindows + " | iex",
                };
            }
            else
            {
                // Use /bin/bash so the script's `$HOME` and shell-quoted args
                // resolve regardless of the user's login shell.
                executable = "/bin/bash";
                args = new List<string>
                {
                    "-c",
                    "curl -LsSf " + InstallerUrlPosix + " | sh",
                };
            }

            int exitCode;
            string stdout;
            string stderr;
            try
            {
                (exitCode, stdout, stderr) = ProcessRunner.Run(executable, args);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[rhino-mcp] uv installer could not be launched: {ex.Message}");
                return false;
            }

            foreach (var line in SplitLines(stdout))
                RhinoApp.WriteLine($"[rhino-mcp] {line}");
            foreach (var line in SplitLines(stderr))
                RhinoApp.WriteLine($"[rhino-mcp] {line}");

            if (exitCode == 0)
            {
                RhinoApp.WriteLine("[rhino-mcp] uv installed.");
                return true;
            }

            RhinoApp.WriteLine($"[rhino-mcp] uv installer exited with code {exitCode}.");
            return false;
        }

        private static IEnumerable<string> SplitLines(string? text)
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
}

using System.Reflection;
using System.Text;
using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;
using Rhino.DocObjects;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Globals exposed to C# scripts executed via Roslyn.
    /// </summary>
    public class CSharpScriptGlobals
    {
        public RhinoDoc doc { get; set; } = null!;
        public StringBuilder output { get; set; } = null!;
    }

    /// <summary>
    /// Handles arbitrary script execution: RhinoScript Python (IronPython)
    /// and RhinoCommon C# (Roslyn).
    /// </summary>
    public class ScriptHandler : HandlerBase
    {
        // ----- Roslyn caching -----
        private static Microsoft.CodeAnalysis.Scripting.ScriptOptions? _scriptOptions;
        private static readonly object _optionsLock = new();

        private static Microsoft.CodeAnalysis.Scripting.ScriptOptions GetScriptOptions()
        {
            if (_scriptOptions != null) return _scriptOptions;

            lock (_optionsLock)
            {
                if (_scriptOptions != null) return _scriptOptions;

                _scriptOptions = Microsoft.CodeAnalysis.Scripting.ScriptOptions.Default
                    .AddReferences(
                        typeof(object).Assembly,
                        typeof(System.Linq.Enumerable).Assembly,
                        typeof(List<>).Assembly,
                        typeof(RhinoDoc).Assembly,
                        typeof(Point3d).Assembly,
                        Assembly.Load("System.Runtime"))
                    .AddImports(
                        "System",
                        "System.Collections.Generic",
                        "System.Linq",
                        "System.Text",
                        "Rhino",
                        "Rhino.Geometry",
                        "Rhino.DocObjects",
                        "Rhino.Commands");

                return _scriptOptions;
            }
        }

        // ----- Python execution -----

        public JObject ExecutePython(JObject parameters)
        {
            var code = parameters["code"]?.ToString()
                ?? throw new ArgumentException("code is required");

            var output = new StringBuilder();
            uint undoRecord = Doc.BeginUndoRecord("MCP: execute_python");

            try
            {
                var pythonScript = Rhino.Runtime.PythonScript.Create();
                if (pythonScript == null)
                    throw new InvalidOperationException(
                        "PythonScript engine not available. Ensure Rhino Python is installed.");

                pythonScript.Output += msg => output.Append(msg);
                pythonScript.SetupScriptContext(Doc);

                bool success = pythonScript.ExecuteScript(code);

                if (!success)
                {
                    return new JObject
                    {
                        ["success"] = false,
                        ["output"] = output.ToString(),
                        ["message"] = "Script execution returned false. Check output for details."
                    };
                }

                return new JObject
                {
                    ["success"] = true,
                    ["output"] = output.ToString(),
                    ["result"] = $"Script executed. Output: {output}"
                };
            }
            catch (Exception ex)
            {
                return new JObject
                {
                    ["success"] = false,
                    ["output"] = output.ToString(),
                    ["message"] = $"{ex.GetType().Name}: {ex.Message}"
                };
            }
            finally
            {
                Doc.EndUndoRecord(undoRecord);
                Doc.Views.Redraw();
            }
        }

        // ----- C# execution -----

        public JObject ExecuteCSharp(JObject parameters)
        {
            var code = parameters["code"]?.ToString()
                ?? throw new ArgumentException("code is required");

            var output = new StringBuilder();
            uint undoRecord = Doc.BeginUndoRecord("MCP: execute_csharp");

            try
            {
                var globals = new CSharpScriptGlobals
                {
                    doc = Doc,
                    output = output
                };

                var options = GetScriptOptions();

                var task = Microsoft.CodeAnalysis.CSharp.Scripting.CSharpScript
                    .EvaluateAsync(code, options, globals, typeof(CSharpScriptGlobals));
                task.Wait();

                return new JObject
                {
                    ["success"] = true,
                    ["output"] = output.ToString(),
                    ["result"] = "Script executed."
                };
            }
            catch (AggregateException ae)
            {
                var inner = ae.InnerException ?? ae;
                return new JObject
                {
                    ["success"] = false,
                    ["output"] = output.ToString(),
                    ["message"] = FormatError(inner, code)
                };
            }
            catch (Microsoft.CodeAnalysis.Scripting.CompilationErrorException ce)
            {
                var errors = new StringBuilder("Compilation failed:\n");
                foreach (var d in ce.Diagnostics)
                    errors.AppendLine($"  {d}");

                return new JObject
                {
                    ["success"] = false,
                    ["output"] = output.ToString(),
                    ["message"] = errors.ToString()
                };
            }
            catch (Exception ex)
            {
                return new JObject
                {
                    ["success"] = false,
                    ["output"] = output.ToString(),
                    ["message"] = FormatError(ex, code)
                };
            }
            finally
            {
                Doc.EndUndoRecord(undoRecord);
                Doc.Views.Redraw();
            }
        }

        private static string FormatError(Exception ex, string code)
        {
            var sb = new StringBuilder();
            sb.AppendLine($"{ex.GetType().Name}: {ex.Message}");
            if (ex.InnerException != null)
                sb.AppendLine($"Inner: {ex.InnerException.Message}");
            return sb.ToString();
        }
    }
}

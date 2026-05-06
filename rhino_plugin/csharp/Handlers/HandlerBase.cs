using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Shared utilities for all command handlers.
    /// </summary>
    public abstract class HandlerBase
    {
        protected static RhinoDoc Doc => RhinoDoc.ActiveDoc;

        protected static Point3d ToPoint(JToken tok)
        {
            return new Point3d(
                tok["x"]?.Value<double>() ?? 0,
                tok["y"]?.Value<double>() ?? 0,
                tok["z"]?.Value<double>() ?? 0);
        }

        protected static Vector3d ToVector(JToken tok)
        {
            return new Vector3d(
                tok["x"]?.Value<double>() ?? 0,
                tok["y"]?.Value<double>() ?? 0,
                tok["z"]?.Value<double>() ?? 0);
        }

        protected static Plane ToPlane(JToken? tok)
        {
            if (tok == null) return Plane.WorldXY;
            var origin = ToPoint(tok["origin"] ?? JObject.FromObject(new { x = 0, y = 0, z = 0 }));
            return new Plane(origin, Vector3d.ZAxis);
        }

        protected static Guid FindId(string guidStr)
        {
            return Guid.Parse(guidStr);
        }

        protected static RhinoObject? FindObject(string guidStr)
        {
            var id = FindId(guidStr);
            return Doc.Objects.FindId(id);
        }

        protected static GeometryBase? FindGeometry(string guidStr)
        {
            return FindObject(guidStr)?.Geometry;
        }

        protected static Curve? FindCurve(string guidStr)
        {
            return FindGeometry(guidStr) as Curve;
        }

        protected static Brep? FindBrep(string guidStr)
        {
            var geom = FindGeometry(guidStr);
            if (geom is Brep brep) return brep;
            if (geom is Extrusion ext) return ext.ToBrep();
            return null;
        }

        protected static Surface? FindSurface(string guidStr)
        {
            var geom = FindGeometry(guidStr);
            if (geom is Surface srf) return srf;
            if (geom is Brep brep && brep.Faces.Count == 1) return brep.Faces[0];
            return null;
        }

        protected static Mesh? FindMesh(string guidStr)
        {
            return FindGeometry(guidStr) as Mesh;
        }

        /// <summary>Add geometry to the document with optional layer/name attributes.</summary>
        protected static Guid AddObject(GeometryBase geometry, JObject parameters)
        {
            var attrs = new ObjectAttributes();

            var layerName = parameters["layer"]?.ToString();
            if (!string.IsNullOrEmpty(layerName))
            {
                var layerIndex = Doc.Layers.FindByFullPath(layerName, -1);
                if (layerIndex < 0)
                {
                    var layer = new Layer { Name = layerName };
                    layerIndex = Doc.Layers.Add(layer);
                }
                attrs.LayerIndex = layerIndex;
            }

            var name = parameters["name"]?.ToString();
            if (!string.IsNullOrEmpty(name))
                attrs.Name = name;

            var id = Doc.Objects.Add(geometry, attrs);
            Doc.Views.Redraw();
            return id;
        }

        /// <summary>Standard success response with object_id and kind.</summary>
        protected static JObject ObjectResult(Guid id, string kind)
        {
            var obj = Doc.Objects.FindId(id);
            var bbox = obj?.Geometry.GetBoundingBox(true) ?? BoundingBox.Empty;

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_id"] = id.ToString(),
                    ["kind"] = kind,
                    ["bbox"] = new JObject
                    {
                        ["min"] = new JObject { ["x"] = bbox.Min.X, ["y"] = bbox.Min.Y, ["z"] = bbox.Min.Z },
                        ["max"] = new JObject { ["x"] = bbox.Max.X, ["y"] = bbox.Max.Y, ["z"] = bbox.Max.Z }
                    }
                },
                ["text"] = $"{kind} created: {id}"
            };
        }

        protected static JObject StatusOk(string message = "ok")
        {
            return new JObject { ["status"] = message };
        }

        /// <summary>
        /// Wraps <see cref="RhinoApp.RunScript(string, bool)"/> with a debug
        /// trace and an emergency <c>_Escape</c> on failure. Use this from
        /// every handler that drives Rhino through scripted commands so a
        /// half-built command (e.g. trailing <c>_Width</c> with no value)
        /// cannot leak to the command line if validation/dispatch throws
        /// mid-sequence.
        /// </summary>
        /// <param name="script">The full RunScript line. Must already include
        /// any required <c>_Enter</c> tokens.</param>
        /// <param name="opName">Short identifier used in the trace prefix
        /// (typically the handler method name).</param>
        /// <summary>Single-arg overload: derives an opName from the call site
        /// (just <c>"runscript"</c>; toggle <c>RHINO_MCP_TRACE_RUNSCRIPT=1</c>
        /// if a more specific tag is needed).</summary>
        protected static void SafeRunScript(string script)
            => SafeRunScript(script, "runscript");

        protected static void SafeRunScript(string script, string opName)
        {
            if (string.IsNullOrWhiteSpace(script))
                throw new System.ArgumentException("SafeRunScript: empty script", nameof(script));

            var traceEnabled = string.Equals(
                System.Environment.GetEnvironmentVariable("RHINO_MCP_TRACE_RUNSCRIPT"),
                "1",
                System.StringComparison.Ordinal);
            if (traceEnabled)
            {
                var rid = BridgeContext.CurrentRequestId;
                var prefix = string.IsNullOrEmpty(rid) ? "" : $"[req:{rid}] ";
                RhinoApp.WriteLine($"[rhino-mcp][runscript:{opName}] {prefix}{script}");
            }

            try
            {
                RhinoApp.RunScript(script, false);
            }
            catch
            {
                // Push an _Escape so any partially-tokenised command
                // (e.g. ``_-ViewCaptureToFile "..." _Width=`` with the value
                // missing) cannot remain pending in Rhino's command line.
                try { RhinoApp.RunScript("_Escape", false); } catch { /* best-effort */ }
                throw;
            }
        }
    }
}

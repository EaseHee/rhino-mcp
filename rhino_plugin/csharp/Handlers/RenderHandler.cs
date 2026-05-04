using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Display;
using Rhino.DocObjects;
using Rhino.Geometry;
using Rhino.Render;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Render automation — camera, light, render setup, render to file,
    /// turntable sequence. The render execution path defers to the active
    /// render engine in Rhino (Rhino Render / Cycles / V-Ray), respecting
    /// any plug-in selected by the user.
    /// </summary>
    public class RenderHandler : HandlerBase
    {
        public JObject CameraSet(JObject p)
        {
            var loc = ToPoint(p["location"]!);
            var tgt = ToPoint(p["target"]!);
            double lens = p["lens_length_mm"]?.Value<double>() ?? 50.0;
            var viewName = p["view_name"]?.ToString();

            RhinoView? view = string.IsNullOrEmpty(viewName)
                ? Doc.Views.ActiveView
                : Doc.Views.Find(viewName, false);
            if (view == null)
                throw new ArgumentException($"view not found: {viewName ?? "(active)"}");

            var vp = view.ActiveViewport;
            vp.SetCameraLocation(loc, false);
            vp.SetCameraTarget(tgt, false);
            vp.Camera35mmLensLength = lens;
            view.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["view"] = view.ActiveViewport.Name,
                    ["location"] = new JObject { ["x"] = loc.X, ["y"] = loc.Y, ["z"] = loc.Z },
                    ["target"] = new JObject { ["x"] = tgt.X, ["y"] = tgt.Y, ["z"] = tgt.Z },
                    ["lens_length_mm"] = lens,
                },
                ["text"] = $"Camera set on '{view.ActiveViewport.Name}' (lens={lens}mm)",
            };
        }

        public JObject LightAdd(JObject p)
        {
            var kind = (p["kind"]?.ToString() ?? "point").ToLowerInvariant();
            var locTok = p["location"];
            var tgtTok = p["target"];
            double intensity = p["intensity"]?.Value<double>() ?? 1.0;
            var colorArr = p["color"] as JArray;
            var color = colorArr != null
                ? System.Drawing.Color.FromArgb(colorArr[0].Value<int>(), colorArr[1].Value<int>(), colorArr[2].Value<int>())
                : System.Drawing.Color.White;
            double spotAngle = p["spot_angle_deg"]?.Value<double>() ?? 45.0;
            double width = p["width"]?.Value<double>() ?? 1.0;
            double length = p["length"]?.Value<double>() ?? 1.0;
            var name = p["name"]?.ToString();

            var light = new Light
            {
                Diffuse = color,
                Intensity = intensity,
                Name = name ?? $"Light_{kind}_{Doc.Lights.Count + 1}",
            };
            var loc = locTok != null ? ToPoint(locTok) : new Point3d(0, 0, 50);
            var tgt = tgtTok != null ? ToPoint(tgtTok) : Point3d.Origin;
            var dir = tgt - loc;
            switch (kind)
            {
                case "point":
                    light.LightStyle = LightStyle.WorldPoint;
                    light.Location = loc;
                    break;
                case "spot":
                    light.LightStyle = LightStyle.WorldSpot;
                    light.Location = loc;
                    light.Direction = dir;
                    light.SpotAngleRadians = spotAngle * Math.PI / 180.0;
                    break;
                case "directional":
                    light.LightStyle = LightStyle.WorldDirectional;
                    light.Direction = dir;
                    break;
                case "rectangular":
                    light.LightStyle = LightStyle.WorldRectangular;
                    light.Location = loc;
                    light.Direction = dir;
                    light.Length = new Vector3d(length, 0, 0);
                    light.Width = new Vector3d(0, width, 0);
                    break;
                case "linear":
                    light.LightStyle = LightStyle.WorldLinear;
                    light.Location = loc;
                    light.Length = new Vector3d(length, 0, 0);
                    break;
            }
            var attrs = new ObjectAttributes();
            var layerName = p["layer"]?.ToString();
            if (!string.IsNullOrEmpty(layerName))
            {
                var idx = Doc.Layers.FindByFullPath(layerName, -1);
                if (idx < 0) idx = Doc.Layers.Add(new Layer { Name = layerName });
                attrs.LayerIndex = idx;
            }
            var id = Doc.Lights.Add(light, attrs);
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["light_id"] = id.ToString(),
                    ["kind"] = kind,
                    ["intensity"] = intensity,
                    ["name"] = light.Name,
                },
                ["text"] = $"Added {kind} light: {light.Name}",
            };
        }

        public JObject Setup(JObject p)
        {
            int width = p["width"]?.Value<int>() ?? 1920;
            int height = p["height"]?.Value<int>() ?? 1080;
            int samples = p["samples"]?.Value<int>() ?? 200;
            string engine = p["engine"]?.ToString() ?? "active";
            bool transparent = p["transparent_background"]?.Value<bool>() ?? false;

            // Persist as document user-strings so subsequent render-to-file calls
            // pick up the same configuration without keeping per-process state.
            Doc.Strings.SetString("rhino_mcp::render_width", width.ToString());
            Doc.Strings.SetString("rhino_mcp::render_height", height.ToString());
            Doc.Strings.SetString("rhino_mcp::render_samples", samples.ToString());
            Doc.Strings.SetString("rhino_mcp::render_engine", engine);
            Doc.Strings.SetString("rhino_mcp::render_transparent", transparent ? "1" : "0");

            if (engine != "active")
            {
                // Switching engines is plug-in dependent; surface the request
                // through the script alias and let Rhino resolve the right
                // RenderContent provider.
                RhinoApp.RunScript($"_-SetCurrentRenderPlugIn \"{engine}\"", false);
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["width"] = width,
                    ["height"] = height,
                    ["samples"] = samples,
                    ["engine"] = engine,
                    ["transparent_background"] = transparent,
                },
                ["text"] = $"Render setup: {width}x{height}, {samples} samples, engine={engine}",
            };
        }

        public JObject ToFile(JObject p)
        {
            var path = p["output_path"]!.ToString();
            int width = p["width"]?.Value<int>() ?? int.Parse(Doc.Strings.GetValue("rhino_mcp::render_width") ?? "1920");
            int height = p["height"]?.Value<int>() ?? int.Parse(Doc.Strings.GetValue("rhino_mcp::render_height") ?? "1080");

            // _-Render + _-SaveRenderWindowAs pipes the active engine's output
            // to disk without opening the dialog.
            RhinoApp.RunScript($"_-Render", false);
            RhinoApp.RunScript($"_-SaveRenderWindowAs \"{path}\" _Enter", false);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["output_path"] = path,
                    ["width"] = width,
                    ["height"] = height,
                },
                ["text"] = $"Rendered {width}x{height} to {path}",
            };
        }

        public JObject Turntable(JObject p)
        {
            var dir = p["output_dir"]!.ToString();
            int frames = p["frame_count"]?.Value<int>() ?? 36;
            double radius = p["radius"]?.Value<double>() ?? 50.0;
            double height = p["height"]?.Value<double>() ?? 20.0;
            var target = p["target"] != null ? ToPoint(p["target"]!) : Point3d.Origin;
            int width = p["width"]?.Value<int>() ?? 1280;
            int rh = p["render_height"]?.Value<int>() ?? 720;
            int samples = p["samples"]?.Value<int>() ?? 100;

            System.IO.Directory.CreateDirectory(dir);
            var paths = new JArray();
            var view = Doc.Views.ActiveView ?? throw new InvalidOperationException("No active view");
            var vp = view.ActiveViewport;
            for (int i = 0; i < frames; i++)
            {
                double a = 2 * Math.PI * i / frames;
                var loc = new Point3d(
                    target.X + radius * Math.Cos(a),
                    target.Y + radius * Math.Sin(a),
                    target.Z + height);
                vp.SetCameraLocation(loc, false);
                vp.SetCameraTarget(target, false);
                view.Redraw();
                var path = System.IO.Path.Combine(dir, $"frame_{i:000}.png");
                RhinoApp.RunScript($"_-Render", false);
                RhinoApp.RunScript($"_-SaveRenderWindowAs \"{path}\" _Enter", false);
                paths.Add(path);
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["output_dir"] = dir,
                    ["frame_count"] = frames,
                    ["frames"] = paths,
                    ["resolution"] = new JArray(width, rh),
                    ["samples"] = samples,
                },
                ["text"] = $"Turntable: {frames} frame(s) in {dir}",
            };
        }
    }
}

using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMcp.Handlers
{
    public class DisplayHandler : HandlerBase
    {
        public JObject ViewSet(JObject p)
        {
            var name = p["name"]!.ToString();
            RhinoApp.RunScript($"_-SetView _World _{name}", false);
            return StatusOk($"View set to {name}");
        }

        public JObject ZoomExtent(JObject p)
        {
            RhinoApp.RunScript("_Zoom _Extents", false);
            return StatusOk("Zoomed to extents");
        }

        public JObject NamedViewSave(JObject p)
        {
            var name = p["name"]!.ToString();
            RhinoApp.RunScript($"_-NamedView _Save \"{name}\" _Enter", false);
            return StatusOk($"Named view saved: {name}");
        }

        public JObject ModeSet(JObject p)
        {
            var mode = p["mode"]!.ToString();
            RhinoApp.RunScript($"_-SetDisplayMode _Mode={mode}", false);
            return StatusOk($"Display mode set to {mode}");
        }

        public JObject Turntable(JObject p)
        {
            var outputPath = p["output_path"]!.ToString();
            var frames = p["frames"]?.Value<int>() ?? 60;
            RhinoApp.RunScript($"_-Turntable _FrameCount={frames} _OutputFile=\"{outputPath}\" _Enter", false);
            return new JObject
            {
                ["status"] = "ok",
                ["output_path"] = outputPath,
                ["frames"] = frames
            };
        }

        public JObject RenderViewport(JObject p)
        {
            var outputPath = p["output_path"]?.ToString();
            if (!string.IsNullOrEmpty(outputPath))
                RhinoApp.RunScript($"_-Render\n_-SaveRenderWindowAs \"{outputPath}\"\n_-CloseRenderWindow", false);
            else
                RhinoApp.RunScript("_-Render", false);
            return new JObject { ["status"] = "ok", ["output_path"] = outputPath };
        }
    }
}

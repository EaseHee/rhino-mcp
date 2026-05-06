using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMcp.Handlers
{
    public class DisplayHandler : HandlerBase
    {
        public JObject ViewSet(JObject p)
        {
            var name = p["name"]!.ToString();
            SafeRunScript($"_-SetView _World _{name}");
            return StatusOk($"View set to {name}");
        }

        public JObject ZoomExtent(JObject p)
        {
            SafeRunScript("_Zoom _Extents");
            return StatusOk("Zoomed to extents");
        }

        public JObject NamedViewSave(JObject p)
        {
            var name = p["name"]!.ToString();
            SafeRunScript($"_-NamedView _Save \"{name}\" _Enter");
            return StatusOk($"Named view saved: {name}");
        }

        public JObject ModeSet(JObject p)
        {
            var mode = p["mode"]!.ToString();
            SafeRunScript($"_-SetDisplayMode _Mode={mode}");
            return StatusOk($"Display mode set to {mode}");
        }

        public JObject Turntable(JObject p)
        {
            var outputPath = p["output_path"]!.ToString();
            var frames = p["frames"]?.Value<int>() ?? 60;
            SafeRunScript($"_-Turntable _FrameCount={frames} _OutputFile=\"{outputPath}\" _Enter");
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
                SafeRunScript($"_-Render\n_-SaveRenderWindowAs \"{outputPath}\"\n_-CloseRenderWindow");
            else
                SafeRunScript("_-Render");
            return new JObject { ["status"] = "ok", ["output_path"] = outputPath };
        }
    }
}

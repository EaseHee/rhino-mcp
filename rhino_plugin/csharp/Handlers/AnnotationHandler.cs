using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMCPBridge.Handlers
{
    public class AnnotationHandler : HandlerBase
    {
        public JObject Text(JObject p)
        {
            var text = p["text"]!.ToString();
            var loc = ToPoint(p["location"]!);
            var height = p["height"]?.Value<double>() ?? 1.0;
            var te = new TextEntity
            {
                PlainText = text,
                TextHeight = height,
                Plane = new Plane(loc, Vector3d.ZAxis)
            };
            var id = Doc.Objects.AddText(te);
            Doc.Views.Redraw();
            return ObjectResult(id, "Text");
        }

        public JObject TextDot(JObject p)
        {
            var text = p["text"]!.ToString();
            var loc = ToPoint(p["location"]!);
            var dot = new TextDot(text, loc);
            var id = AddObject(dot, p);
            return ObjectResult(id, "TextDot");
        }

        public JObject DimLinear(JObject p)
        {
            RhinoApp.RunScript("_DimLinear", false);
            return StatusOk("DimLinear command invoked");
        }

        public JObject DimAligned(JObject p)
        {
            RhinoApp.RunScript("_DimAligned", false);
            return StatusOk("DimAligned command invoked");
        }

        public JObject DimAngular(JObject p)
        {
            RhinoApp.RunScript("_DimAngle", false);
            return StatusOk("DimAngular command invoked");
        }

        public JObject Leader(JObject p)
        {
            RhinoApp.RunScript("_Leader", false);
            return StatusOk("Leader command invoked");
        }

        public JObject Hatch(JObject p)
        {
            RhinoApp.RunScript("_Hatch", false);
            return StatusOk("Hatch command invoked");
        }

        public JObject ClippingPlane(JObject p)
        {
            var origin = ToPoint(p["origin"]!);
            var normal = p["normal"] != null ? ToVector(p["normal"]!) : Vector3d.ZAxis;
            var plane = new Plane(origin, normal);
            var w = p["width"]?.Value<double>() ?? 10.0;
            var h = p["height"]?.Value<double>() ?? 10.0;
            var id = Doc.Objects.AddClippingPlane(plane, w, h, Doc.Views.ActiveView.ActiveViewportID);
            Doc.Views.Redraw();
            return ObjectResult(id, "ClippingPlane");
        }
    }
}

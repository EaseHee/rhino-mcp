using Newtonsoft.Json.Linq;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    public class CurveHandler : HandlerBase
    {
        public JObject Length(JObject p)
        {
            var curve = FindCurve(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Curve not found");
            return new JObject
            {
                ["summary"] = new JObject { ["length"] = curve.GetLength() },
                ["text"] = $"Curve length: {curve.GetLength():F4}"
            };
        }

        public JObject PointAt(JObject p)
        {
            var curve = FindCurve(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Curve not found");
            var t = p["t"]!.Value<double>();
            var domain = curve.Domain;
            if (t < domain.Min || t > domain.Max)
                throw new ArgumentOutOfRangeException("t", $"Parameter {t} outside domain [{domain.Min}, {domain.Max}]");
            var pt = curve.PointAt(t);
            var tan = curve.TangentAt(t);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["point"] = new JObject { ["x"] = pt.X, ["y"] = pt.Y, ["z"] = pt.Z },
                    ["tangent"] = new JObject { ["x"] = tan.X, ["y"] = tan.Y, ["z"] = tan.Z }
                }
            };
        }

        public JObject Split(JObject p)
        {
            var curve = FindCurve(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Curve not found");
            var parameters = p["parameters"]!.Select(t => t.Value<double>()).ToArray();
            var pieces = curve.Split(parameters);
            if (pieces == null || pieces.Length == 0)
                throw new InvalidOperationException("Split produced no segments");
            var ids = new JArray();
            foreach (var piece in pieces)
            {
                var id = AddObject(piece, p);
                ids.Add(id.ToString());
            }
            return new JObject
            {
                ["summary"] = new JObject { ["pieces"] = ids },
                ["text"] = $"Split into {pieces.Length} segments"
            };
        }
    }
}

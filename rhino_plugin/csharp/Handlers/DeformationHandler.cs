using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMCPBridge.Handlers
{
    /// <summary>
    /// Deformation operations: bend, twist, taper, flow along curve.
    /// Uses SpaceMorph API from RhinoCommon.
    /// </summary>
    public class DeformationHandler : HandlerBase
    {
        public JObject Bend(JObject p)
        {
            var ids = GetIds(p);
            var start = ToPoint(p["start"]!);
            var end = ToPoint(p["end"]!);
            var through = ToPoint(p["point"]!);
            bool copy = p["make_copy"]?.Value<bool>() ?? false;

            uint undo = Doc.BeginUndoRecord("MCP: bend");
            try
            {
                var line = new Line(start, end);
                var morph = new Rhino.Geometry.Morphs.BendSpaceMorph(
                    start, end, through, true, false);

                return ApplyMorph(ids, morph, copy, "Bend");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject Twist(JObject p)
        {
            var ids = GetIds(p);
            var axisStart = ToPoint(p["axis_start"]!);
            var axisEnd = ToPoint(p["axis_end"]!);
            double angleDeg = p["angle_degrees"]!.Value<double>();
            bool copy = p["make_copy"]?.Value<bool>() ?? false;

            uint undo = Doc.BeginUndoRecord("MCP: twist");
            try
            {
                double radians = angleDeg * Math.PI / 180.0;
                var morph = new Rhino.Geometry.Morphs.TwistSpaceMorph();
                morph.TwistAxis = new Line(axisStart, axisEnd);
                morph.TwistAngleRadians = radians;

                return ApplyMorph(ids, morph, copy, "Twist");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject Taper(JObject p)
        {
            var ids = GetIds(p);
            var axisStart = ToPoint(p["axis_start"]!);
            var axisEnd = ToPoint(p["axis_end"]!);
            double startRadius = p["start_radius"]!.Value<double>();
            double endRadius = p["end_radius"]!.Value<double>();
            bool copy = p["make_copy"]?.Value<bool>() ?? false;

            uint undo = Doc.BeginUndoRecord("MCP: taper");
            try
            {
                var morph = new Rhino.Geometry.Morphs.TaperSpaceMorph(
                    axisStart, axisEnd, startRadius, endRadius, false, false);

                return ApplyMorph(ids, morph, copy, "Taper");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject FlowAlongCurve(JObject p)
        {
            var ids = GetIds(p);
            var baseCrv = FindCurve(p["base_curve_id"]!.ToString())
                ?? throw new ArgumentException("Base curve not found");
            var targetCrv = FindCurve(p["target_curve_id"]!.ToString())
                ?? throw new ArgumentException("Target curve not found");
            bool copy = p["make_copy"]?.Value<bool>() ?? true;

            uint undo = Doc.BeginUndoRecord("MCP: flow_along_curve");
            try
            {
                var morph = new Rhino.Geometry.Morphs.FlowSpaceMorph(
                    baseCrv, targetCrv, false);

                return ApplyMorph(ids, morph, copy, "Flow");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        private static List<string> GetIds(JObject p)
        {
            var arr = p["object_ids"] as JArray
                ?? throw new ArgumentException("object_ids required");
            return arr.Select(t => t.ToString()).ToList();
        }

        private JObject ApplyMorph(List<string> ids, SpaceMorph morph, bool copy, string op)
        {
            var resultIds = new JArray();
            foreach (var idStr in ids)
            {
                var obj = FindObject(idStr);
                if (obj == null) continue;

                var geom = obj.Geometry.Duplicate();
                if (morph.Morph(geom))
                {
                    Guid newId;
                    if (copy)
                    {
                        newId = Doc.Objects.Add(geom, obj.Attributes);
                    }
                    else
                    {
                        // Delete original + add morphed with same attributes
                        var attrs = obj.Attributes.Duplicate();
                        Doc.Objects.Delete(obj, true);
                        newId = Doc.Objects.Add(geom, attrs);
                    }
                    resultIds.Add(newId.ToString());
                }
            }

            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_ids"] = resultIds },
                ["text"] = $"{op} applied to {resultIds.Count} object(s)"
            };
        }
    }
}

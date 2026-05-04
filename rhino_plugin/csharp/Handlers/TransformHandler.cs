using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    public class TransformHandler : HandlerBase
    {
        public JObject Move(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var vec = ToVector(p["translation"]!);
            var xform = Transform.Translation(vec);
            return ApplyTransform(ids, xform, "Move");
        }

        public JObject Rotate(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var center = ToPoint(p["center"]!);
            var angle = RhinoMath.ToRadians(p["angle_degrees"]!.Value<double>());
            var axis = p["axis"] != null ? ToVector(p["axis"]!) : Vector3d.ZAxis;
            var xform = Transform.Rotation(angle, axis, center);
            return ApplyTransform(ids, xform, "Rotate");
        }

        public JObject Scale(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var center = ToPoint(p["center"]!);
            var factor = p["factor"]!.Value<double>();
            var xform = Transform.Scale(center, factor);
            return ApplyTransform(ids, xform, "Scale");
        }

        public JObject Mirror(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var origin = ToPoint(p["plane_origin"]!);
            var normal = ToVector(p["plane_normal"]!);
            var plane = new Plane(origin, normal);
            var xform = Transform.Mirror(plane);
            var newIds = new JArray();
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj == null) continue;
                var dup = obj.Geometry.Duplicate();
                dup.Transform(xform);
                var newId = Doc.Objects.Add(dup, obj.Attributes);
                newIds.Add(newId.ToString());
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["new_ids"] = newIds, ["kind"] = "Mirror" },
                ["text"] = $"Mirrored {newIds.Count} objects"
            };
        }

        public JObject Orient(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var fromPlane = ToPlane(p["from_plane"]);
            var toPlane = ToPlane(p["to_plane"]);
            var xform = Transform.PlaneToPlane(fromPlane, toPlane);
            return ApplyTransform(ids, xform, "Orient");
        }

        public JObject ArrayLinear(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var dir = ToVector(p["direction"]!);
            var count = p["count"]!.Value<int>();
            var spacing = p["spacing"]!.Value<double>();
            dir.Unitize();
            var newIds = new JArray();
            for (int i = 1; i < count; i++)
            {
                var xform = Transform.Translation(dir * spacing * i);
                foreach (var id in ids)
                {
                    var obj = Doc.Objects.FindId(id);
                    if (obj == null) continue;
                    var dup = obj.Geometry.Duplicate();
                    dup.Transform(xform);
                    newIds.Add(Doc.Objects.Add(dup, obj.Attributes).ToString());
                }
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["new_ids"] = newIds, ["kind"] = "ArrayLinear" },
                ["text"] = $"ArrayLinear: {newIds.Count} copies"
            };
        }

        public JObject ArrayPolar(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var center = ToPoint(p["center"]!);
            var count = p["count"]!.Value<int>();
            var totalAngle = RhinoMath.ToRadians(p["angle_degrees"]?.Value<double>() ?? 360);
            var axis = p["axis"] != null ? ToVector(p["axis"]!) : Vector3d.ZAxis;
            var newIds = new JArray();
            for (int i = 1; i < count; i++)
            {
                var angle = totalAngle * i / count;
                var xform = Transform.Rotation(angle, axis, center);
                foreach (var id in ids)
                {
                    var obj = Doc.Objects.FindId(id);
                    if (obj == null) continue;
                    var dup = obj.Geometry.Duplicate();
                    dup.Transform(xform);
                    newIds.Add(Doc.Objects.Add(dup, obj.Attributes).ToString());
                }
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["new_ids"] = newIds, ["kind"] = "ArrayPolar" },
                ["text"] = $"ArrayPolar: {newIds.Count} copies"
            };
        }

        public JObject Flow(JObject p) =>
            RunScript($"_Flow _SelId {p["object_ids"]!.First} _Enter", "Flow");

        public JObject CageEdit(JObject p) =>
            RunScript($"_CageEdit _SelId {p["object_ids"]!.First} _Enter", "CageEdit");

        public JObject SelectionBbox(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var bbox = BoundingBox.Empty;
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj != null) bbox.Union(obj.Geometry.GetBoundingBox(true));
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["min"] = new JObject { ["x"] = bbox.Min.X, ["y"] = bbox.Min.Y, ["z"] = bbox.Min.Z },
                    ["max"] = new JObject { ["x"] = bbox.Max.X, ["y"] = bbox.Max.Y, ["z"] = bbox.Max.Z }
                }
            };
        }

        private JObject ApplyTransform(List<Guid> ids, Transform xform, string kind)
        {
            foreach (var id in ids)
                Doc.Objects.Transform(id, xform, true);
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_ids"] = new JArray(ids.Select(i => i.ToString())), ["kind"] = kind },
                ["text"] = $"{kind}: {ids.Count} objects"
            };
        }

        private static JObject RunScript(string script, string kind)
        {
            RhinoApp.RunScript(script, false);
            return new JObject { ["status"] = "ok", ["kind"] = kind };
        }
    }
}

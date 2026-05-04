using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    public class SolidHandler : HandlerBase
    {
        public JObject Box(JObject p)
        {
            var corner = ToPoint(p["corner"]!);
            var sx = p["size_x"]!.Value<double>();
            var sy = p["size_y"]!.Value<double>();
            var sz = p["size_z"]!.Value<double>();
            var box = new Box(Plane.WorldXY,
                new Interval(corner.X, corner.X + sx),
                new Interval(corner.Y, corner.Y + sy),
                new Interval(corner.Z, corner.Z + sz));
            var brep = box.ToBrep();
            var id = AddObject(brep, p);
            return ObjectResult(id, "Box");
        }

        public JObject Sphere(JObject p)
        {
            var center = ToPoint(p["center"]!);
            var radius = p["radius"]!.Value<double>();
            var sphere = new Rhino.Geometry.Sphere(center, radius);
            var id = Doc.Objects.AddSphere(sphere);
            Doc.Views.Redraw();
            return ObjectResult(id, "Sphere");
        }

        public JObject Cylinder(JObject p)
        {
            var center = ToPoint(p["base_center"]!);
            var radius = p["radius"]!.Value<double>();
            var height = p["height"]!.Value<double>();
            var axis = p["axis"] != null ? ToVector(p["axis"]!) : Vector3d.ZAxis;
            var plane = new Plane(center, axis);
            var circle = new Circle(plane, radius);
            var cyl = new Rhino.Geometry.Cylinder(circle, height);
            var capped = p["capped"]?.Value<bool>() ?? true;
            var brep = cyl.ToBrep(capped, capped);
            var id = AddObject(brep, p);
            return ObjectResult(id, "Cylinder");
        }

        public JObject Cone(JObject p)
        {
            var center = ToPoint(p["base_center"]!);
            var radius = p["radius"]!.Value<double>();
            var height = p["height"]!.Value<double>();
            var plane = new Plane(center, Vector3d.ZAxis);
            var cone = new Rhino.Geometry.Cone(plane, height, radius);
            var capped = p["capped"]?.Value<bool>() ?? true;
            var brep = cone.ToBrep(capped);
            var id = AddObject(brep, p);
            return ObjectResult(id, "Cone");
        }

        public JObject Torus(JObject p)
        {
            var center = ToPoint(p["center"]!);
            var majorR = p["major_radius"]!.Value<double>();
            var minorR = p["minor_radius"]!.Value<double>();
            var plane = new Plane(center, Vector3d.ZAxis);
            var torus = new Rhino.Geometry.Torus(plane, majorR, minorR);
            var srf = torus.ToRevSurface().ToBrep();
            var id = AddObject(srf, p);
            return ObjectResult(id, "Torus");
        }

        public JObject BooleanUnion(JObject p)
        {
            var breps = ResolveBreps(p["object_ids"]!);
            var result = Brep.CreateBooleanUnion(breps, Doc.ModelAbsoluteTolerance);
            return BooleanResult(result, p, "BooleanUnion");
        }

        public JObject BooleanDifference(JObject p)
        {
            var a = ResolveBreps(p["a_ids"]!);
            var b = ResolveBreps(p["b_ids"]!);
            var result = Brep.CreateBooleanDifference(a, b, Doc.ModelAbsoluteTolerance);
            return BooleanResult(result, p, "BooleanDifference");
        }

        public JObject BooleanIntersection(JObject p)
        {
            var a = ResolveBreps(p["a_ids"]!);
            var b = ResolveBreps(p["b_ids"]!);
            var result = Brep.CreateBooleanIntersection(a, b, Doc.ModelAbsoluteTolerance);
            return BooleanResult(result, p, "BooleanIntersection");
        }

        public JObject CapHoles(JObject p)
        {
            var brep = FindBrep(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Brep not found");
            var capped = brep.CapPlanarHoles(Doc.ModelAbsoluteTolerance);
            if (capped == null) throw new InvalidOperationException("Cap failed");
            var id = AddObject(capped, p);
            return ObjectResult(id, "CappedBrep");
        }

        public JObject Shell(JObject p)
        {
            var brep = FindBrep(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Brep not found");
            var thickness = p["thickness"]!.Value<double>();
            var faceIndices = p["face_indices"]?.Select(t => t.Value<int>()).ToArray()
                ?? Array.Empty<int>();
            var result = Brep.CreateShell(brep, faceIndices, thickness,
                Doc.ModelAbsoluteTolerance);
            if (result == null || result.Length == 0)
                throw new InvalidOperationException("Shell failed");
            var id = AddObject(result[0], p);
            return ObjectResult(id, "Shell");
        }

        private List<Brep> ResolveBreps(JToken ids)
        {
            return ids.Select(t =>
                FindBrep(t.ToString()) ?? throw new KeyNotFoundException($"Brep not found: {t}")
            ).ToList();
        }

        private JObject BooleanResult(Brep[]? result, JObject p, string kind)
        {
            if (result == null || result.Length == 0)
                throw new InvalidOperationException($"{kind} produced no result");
            var newIds = new JArray();
            foreach (var brep in result)
            {
                var id = AddObject(brep, p);
                newIds.Add(id.ToString());
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_ids"] = newIds, ["kind"] = kind },
                ["text"] = $"{kind}: {result.Length} object(s)"
            };
        }
    }
}

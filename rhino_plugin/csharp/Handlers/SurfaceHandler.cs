using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    public class SurfaceHandler : HandlerBase
    {
        public JObject PlaneSurface(JObject p)
        {
            var plane = ToPlane(p["plane"]);
            var w = p["width"]!.Value<double>();
            var h = p["height"]!.Value<double>();
            var srf = new PlaneSurface(plane,
                new Interval(-w / 2, w / 2),
                new Interval(-h / 2, h / 2));
            var id = AddObject(srf, p);
            return ObjectResult(id, "PlaneSurface");
        }

        public JObject Extrude(JObject p)
        {
            var curve = FindCurve(p["profile_id"]!.ToString())
                ?? throw new KeyNotFoundException("Profile curve not found");
            var dir = ToVector(p["direction"]!);
            var dist = p["distance"]!.Value<double>();
            dir.Unitize();
            var srf = Surface.CreateExtrusion(curve, dir * dist);
            if (srf == null) throw new InvalidOperationException("Extrusion failed");
            var brep = srf.ToBrep();
            var capped = p["capped"]?.Value<bool>() ?? true;
            if (capped) brep = brep.CapPlanarHoles(Doc.ModelAbsoluteTolerance) ?? brep;
            var id = AddObject(brep, p);
            return ObjectResult(id, "Extrusion");
        }

        public JObject Revolve(JObject p)
        {
            var curve = FindCurve(p["profile_id"]!.ToString())
                ?? throw new KeyNotFoundException("Profile curve not found");
            var axisStart = ToPoint(p["axis_start"]!);
            var axisEnd = ToPoint(p["axis_end"]!);
            var angle = RhinoMath.ToRadians(p["angle_degrees"]?.Value<double>() ?? 360);
            var axis = new Line(axisStart, axisEnd);
            var srf = RevSurface.Create(curve, axis, 0, angle);
            if (srf == null) throw new InvalidOperationException("Revolve failed");
            var id = AddObject(srf.ToBrep(), p);
            return ObjectResult(id, "Revolve");
        }

        public JObject Loft(JObject p)
        {
            var curves = p["profile_ids"]!.Select(t =>
                FindCurve(t.ToString()) ?? throw new KeyNotFoundException($"Curve not found: {t}")
            ).ToList();
            var closed = p["closed"]?.Value<bool>() ?? false;
            var loftType = p["loft_type"]?.ToString()?.ToLower() switch
            {
                "loose" => LoftType.Loose,
                "tight" => LoftType.Tight,
                "straight" => LoftType.Straight,
                "uniform" => LoftType.Uniform,
                _ => LoftType.Normal
            };
            var breps = Brep.CreateFromLoft(curves, Point3d.Unset, Point3d.Unset, loftType, closed);
            if (breps == null || breps.Length == 0)
                throw new InvalidOperationException("Loft failed");
            var id = AddObject(breps[0], p);
            return ObjectResult(id, "Loft");
        }

        public JObject Sweep1(JObject p)
        {
            var rail = FindCurve(p["rail_id"]!.ToString())
                ?? throw new KeyNotFoundException("Rail curve not found");
            var profiles = p["profile_ids"]!.Select(t =>
                FindCurve(t.ToString()) ?? throw new KeyNotFoundException($"Profile not found: {t}")
            ).ToList();
            var breps = Brep.CreateFromSweep(rail, profiles,
                closed: false, Doc.ModelAbsoluteTolerance);
            if (breps == null || breps.Length == 0)
                throw new InvalidOperationException("Sweep1 failed");
            var id = AddObject(breps[0], p);
            return ObjectResult(id, "Sweep1");
        }

        public JObject Sweep2(JObject p)
        {
            var rail1 = FindCurve(p["rail1_id"]!.ToString())
                ?? throw new KeyNotFoundException("Rail1 not found");
            var rail2 = FindCurve(p["rail2_id"]!.ToString())
                ?? throw new KeyNotFoundException("Rail2 not found");
            var profiles = p["profile_ids"]!.Select(t =>
                FindCurve(t.ToString()) ?? throw new KeyNotFoundException($"Profile not found: {t}")
            ).ToList();
            var breps = Brep.CreateFromSweep(rail1, rail2, profiles,
                false, Doc.ModelAbsoluteTolerance);
            if (breps == null || breps.Length == 0)
                throw new InvalidOperationException("Sweep2 failed");
            var id = AddObject(breps[0], p);
            return ObjectResult(id, "Sweep2");
        }

        public JObject NetworkSurface(JObject p)
        {
            var uCurves = p["u_curve_ids"]!.Select(t =>
                FindCurve(t.ToString()) ?? throw new KeyNotFoundException($"U-curve not found: {t}")
            ).ToList();
            var vCurves = p["v_curve_ids"]!.Select(t =>
                FindCurve(t.ToString()) ?? throw new KeyNotFoundException($"V-curve not found: {t}")
            ).ToList();
            var allCurves = uCurves.Concat(vCurves);
            int error;
            var srf = NurbsSurface.CreateNetworkSurface(
                allCurves, 0, Doc.ModelAbsoluteTolerance,
                Doc.ModelAbsoluteTolerance, Doc.ModelAngleToleranceRadians, out error);
            if (srf == null)
                throw new InvalidOperationException($"NetworkSurface failed (error code {error})");
            var id = AddObject(srf, p);
            return ObjectResult(id, "NetworkSurface");
        }

        public JObject Patch(JObject p)
        {
            var curves = p["boundary_curve_ids"]!.Select(t =>
                FindCurve(t.ToString()) ?? throw new KeyNotFoundException($"Boundary not found: {t}")
            ).ToArray();
            var spans = p["span_count"]?.Value<int>() ?? 10;
            var brep = Brep.CreatePatch(curves, spans, spans, Doc.ModelAbsoluteTolerance);
            if (brep == null) throw new InvalidOperationException("Patch failed");
            var id = AddObject(brep, p);
            return ObjectResult(id, "Patch");
        }

        public JObject BlendSurface(JObject p)
        {
            // Blend between two surface edges
            var faceA = FindBrep(p["edge_a_id"]!.ToString());
            var faceB = FindBrep(p["edge_b_id"]!.ToString());
            if (faceA == null || faceB == null)
                throw new KeyNotFoundException("Surface edge not found");
            // Use RhinoScript command as fallback for complex blend
            var script = $"_BlendSrf _SelId {p["edge_a_id"]} _SelId {p["edge_b_id"]} _Enter";
            SafeRunScript(script);
            return StatusOk("BlendSurface command executed");
        }

        public JObject FilletSurface(JObject p)
        {
            var radius = p["radius"]!.Value<double>();
            var script = $"_FilletSrf _Radius {radius} _SelId {p["surface_a_id"]} _SelId {p["surface_b_id"]} _Enter";
            SafeRunScript(script);
            return StatusOk("FilletSurface command executed");
        }

        public JObject OffsetSurface(JObject p)
        {
            var srf = FindSurface(p["surface_id"]!.ToString())
                ?? throw new KeyNotFoundException("Surface not found");
            var dist = p["distance"]!.Value<double>();
            var tol = p["tolerance"]?.Value<double>() ?? Doc.ModelAbsoluteTolerance;
            var offset = srf.Offset(dist, tol);
            if (offset == null) throw new InvalidOperationException("Offset failed");
            var id = AddObject(offset, p);
            return ObjectResult(id, "OffsetSurface");
        }
    }
}

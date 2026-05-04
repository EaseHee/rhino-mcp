using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    public class GeometryHandler : HandlerBase
    {
        public JObject Point(JObject p)
        {
            var pt = ToPoint(p["point"]!);
            var id = AddObject(new Rhino.Geometry.Point(pt), p);
            return ObjectResult(id, "Point");
        }

        public JObject Line(JObject p)
        {
            var line = new LineCurve(ToPoint(p["start"]!), ToPoint(p["end"]!));
            var id = AddObject(line, p);
            return ObjectResult(id, "Line");
        }

        public JObject Polyline(JObject p)
        {
            var pts = p["points"]!.Select(t => ToPoint(t)).ToList();
            var closed = p["closed"]?.Value<bool>() ?? false;
            if (closed && pts.Count > 0 && pts[0] != pts[^1])
                pts.Add(pts[0]);
            var pl = new PolylineCurve(pts);
            var id = AddObject(pl, p);
            return ObjectResult(id, "Polyline");
        }

        public JObject Arc(JObject p)
        {
            var plane = ToPlane(p["plane"]);
            var radius = p["radius"]!.Value<double>();
            var angle = p["angle_degrees"]!.Value<double>();
            var arc = new Rhino.Geometry.Arc(plane, radius, RhinoMath.ToRadians(angle));
            var id = AddObject(new ArcCurve(arc), p);
            return ObjectResult(id, "Arc");
        }

        public JObject Circle(JObject p)
        {
            var center = ToPoint(p["center"]!);
            var radius = p["radius"]!.Value<double>();
            var circle = new Rhino.Geometry.Circle(center, radius);
            var id = AddObject(new ArcCurve(circle), p);
            return ObjectResult(id, "Circle");
        }

        public JObject Ellipse(JObject p)
        {
            var center = ToPoint(p["center"]!);
            var rx = p["radius_x"]!.Value<double>();
            var ry = p["radius_y"]!.Value<double>();
            var ellipse = new Rhino.Geometry.Ellipse(new Plane(center, Vector3d.ZAxis), rx, ry);
            var id = AddObject(ellipse.ToNurbsCurve(), p);
            return ObjectResult(id, "Ellipse");
        }

        public JObject Rectangle(JObject p)
        {
            var corner = ToPoint(p["corner"]!);
            var w = p["width"]!.Value<double>();
            var h = p["height"]!.Value<double>();
            var plane = new Plane(corner, Vector3d.ZAxis);
            var rect = new Rhino.Geometry.Rectangle3d(plane, w, h);
            var id = AddObject(rect.ToPolyline().ToPolylineCurve(), p);
            return ObjectResult(id, "Rectangle");
        }

        public JObject Polygon(JObject p)
        {
            var center = ToPoint(p["center"]!);
            var radius = p["radius"]!.Value<double>();
            var sides = p["sides"]!.Value<int>();
            var pts = new List<Point3d>();
            for (int i = 0; i <= sides; i++)
            {
                var angle = 2 * Math.PI * i / sides;
                pts.Add(new Point3d(
                    center.X + radius * Math.Cos(angle),
                    center.Y + radius * Math.Sin(angle),
                    center.Z));
            }
            var id = AddObject(new PolylineCurve(pts), p);
            return ObjectResult(id, "Polygon");
        }

        public JObject NurbsCurve(JObject p)
        {
            var cps = p["control_points"]!.Select(t => ToPoint(t)).ToList();
            var degree = p["degree"]!.Value<int>();
            var curve = Rhino.Geometry.NurbsCurve.Create(false, degree, cps);
            if (curve == null)
                throw new ArgumentException("Failed to create NURBS curve with given control points and degree");
            var id = AddObject(curve, p);
            return ObjectResult(id, "NurbsCurve");
        }

        public JObject Helix(JObject p)
        {
            var axis = new Line(ToPoint(p["axis_start"]!), ToPoint(p["axis_end"]!));
            var startPt = ToPoint(p["start_point"]!);
            var turns = p["turns"]!.Value<double>();
            var pitch = axis.Length / turns;
            var helix = Rhino.Geometry.NurbsCurve.CreateSpiral(
                axis.From, axis.Direction, startPt, pitch, turns, 1.0, 1.0);
            if (helix == null)
                throw new ArgumentException("Failed to create helix");
            var id = AddObject(helix, p);
            return ObjectResult(id, "Helix");
        }

        public JObject Spiral(JObject p)
        {
            // Spiral as a planar helix with increasing radius
            var center = ToPoint(p["center"]!);
            var rStart = p["radius_start"]!.Value<double>();
            var rEnd = p["radius_end"]!.Value<double>();
            var turns = p["turns"]!.Value<double>();
            var pts = new List<Point3d>();
            int count = (int)(turns * 36);
            for (int i = 0; i <= count; i++)
            {
                var t = (double)i / count;
                var angle = 2 * Math.PI * turns * t;
                var r = rStart + (rEnd - rStart) * t;
                pts.Add(new Point3d(center.X + r * Math.Cos(angle), center.Y + r * Math.Sin(angle), center.Z));
            }
            var curve = Rhino.Geometry.NurbsCurve.Create(false, 3, pts);
            if (curve == null)
                throw new ArgumentException("Failed to create spiral");
            var id = AddObject(curve, p);
            return ObjectResult(id, "Spiral");
        }
    }
}

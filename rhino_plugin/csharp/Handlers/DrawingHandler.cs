using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Drawing-set tools — sheet, view placement, section cut, title block, PDF export.
    /// Uses RhinoCommon's Make2D pipeline through RhinoApp.RunScript when a direct API
    /// is not available, and falls back to projecting wireframes onto the sheet plane.
    /// </summary>
    public class DrawingHandler : HandlerBase
    {
        private const string SheetMetaKeyName = "sheet_name";
        private const string SheetMetaKeyW = "sheet_width_mm";
        private const string SheetMetaKeyH = "sheet_height_mm";
        private const string SheetMetaKeyScale = "sheet_scale";
        private const string SheetMetaKeyOrigin = "sheet_origin";

        private static int EnsureLayer(string fullPath)
        {
            var idx = Doc.Layers.FindByFullPath(fullPath, -1);
            if (idx >= 0) return idx;
            // Create nested layers as needed using "::" separator.
            var parts = fullPath.Split(new[] { "::" }, StringSplitOptions.None);
            var parentIdx = -1;
            for (int i = 0; i < parts.Length; i++)
            {
                var soFar = string.Join("::", parts.Take(i + 1));
                var existing = Doc.Layers.FindByFullPath(soFar, -1);
                if (existing >= 0)
                {
                    parentIdx = existing;
                    continue;
                }
                var layer = new Layer { Name = parts[i] };
                if (parentIdx >= 0) layer.ParentLayerId = Doc.Layers[parentIdx].Id;
                parentIdx = Doc.Layers.Add(layer);
            }
            return parentIdx;
        }

        public JObject SheetCreate(JObject p)
        {
            var name = p["name"]!.ToString();
            var w = p["width_mm"]?.Value<double>() ?? 420.0;
            var h = p["height_mm"]?.Value<double>() ?? 297.0;
            var scale = p["scale_denominator"]?.Value<int>() ?? 100;
            var originTok = p["origin"];
            var origin = originTok != null ? ToPoint(originTok) : Point3d.Origin;

            var layerIdx = EnsureLayer($"Sheets::{name}");
            var poly = new Polyline
            {
                new Point3d(origin.X, origin.Y, origin.Z),
                new Point3d(origin.X + w, origin.Y, origin.Z),
                new Point3d(origin.X + w, origin.Y + h, origin.Z),
                new Point3d(origin.X, origin.Y + h, origin.Z),
                new Point3d(origin.X, origin.Y, origin.Z),
            };
            var attrs = new ObjectAttributes { LayerIndex = layerIdx, Name = $"sheet_{name}" };
            attrs.SetUserString(SheetMetaKeyName, name);
            attrs.SetUserString(SheetMetaKeyW, w.ToString("R"));
            attrs.SetUserString(SheetMetaKeyH, h.ToString("R"));
            attrs.SetUserString(SheetMetaKeyScale, scale.ToString());
            attrs.SetUserString(SheetMetaKeyOrigin, $"{origin.X},{origin.Y},{origin.Z}");
            var id = Doc.Objects.AddPolyline(poly, attrs);
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["sheet_id"] = id.ToString(),
                    ["name"] = name,
                    ["width_mm"] = w,
                    ["height_mm"] = h,
                    ["scale_denominator"] = scale,
                    ["layer"] = $"Sheets::{name}",
                },
                ["text"] = $"Sheet '{name}' ({w}x{h} mm @1:{scale})",
            };
        }

        private static (string name, Point3d origin, double w, double h, int scale) ReadSheetMeta(string sheetId)
        {
            var obj = FindObject(sheetId)
                ?? throw new InvalidOperationException($"sheet not found: {sheetId}");
            var name = obj.Attributes.GetUserString(SheetMetaKeyName);
            if (string.IsNullOrEmpty(name))
                throw new ArgumentException("sheet_id does not refer to a sheet (missing user_text metadata)");
            var w = double.Parse(obj.Attributes.GetUserString(SheetMetaKeyW) ?? "0");
            var h = double.Parse(obj.Attributes.GetUserString(SheetMetaKeyH) ?? "0");
            var scale = int.TryParse(obj.Attributes.GetUserString(SheetMetaKeyScale) ?? "100", out var s) ? s : 100;
            var originRaw = obj.Attributes.GetUserString(SheetMetaKeyOrigin) ?? "0,0,0";
            var parts = originRaw.Split(',');
            var origin = parts.Length == 3
                ? new Point3d(double.Parse(parts[0]), double.Parse(parts[1]), double.Parse(parts[2]))
                : Point3d.Origin;
            return (name, origin, w, h, scale);
        }

        public JObject ViewPlace(JObject p)
        {
            var sheetId = p["sheet_id"]!.ToString();
            var meta = ReadSheetMeta(sheetId);
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var plane = (p["view_plane"]?.ToString() ?? "Top");
            var target = ToPoint(p["target_origin"]!);
            var scale = p["viewport_scale"]?.Value<double>() ?? 0.01;
            var layerIdx = EnsureLayer(p["layer"]?.ToString() ?? $"Sheets::{meta.name}");

            // Project each object's wireframe onto the chosen view plane and translate to target.
            var newIds = new JArray();
            var basis = ViewBasis(plane);
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj == null) continue;
                var wires = ExtractWireframe(obj.Geometry);
                foreach (var crv in wires)
                {
                    var projected = ProjectCurve(crv, basis, target, scale);
                    if (projected == null) continue;
                    var attrs = new ObjectAttributes { LayerIndex = layerIdx };
                    attrs.SetUserString("sheet_id", sheetId);
                    attrs.SetUserString("source_object_id", id.ToString());
                    attrs.SetUserString("view_plane", plane);
                    var nid = Doc.Objects.AddCurve(projected, attrs);
                    newIds.Add(nid.ToString());
                }
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["sheet_id"] = sheetId,
                    ["object_ids"] = newIds,
                    ["view_plane"] = plane,
                    ["scale"] = scale,
                },
                ["text"] = $"Placed view '{plane}' with {newIds.Count} curve(s)",
            };
        }

        private static (Vector3d u, Vector3d v, Vector3d n) ViewBasis(string plane)
        {
            return plane.ToLowerInvariant() switch
            {
                "top" => (Vector3d.XAxis, Vector3d.YAxis, Vector3d.ZAxis),
                "bottom" => (Vector3d.XAxis, -Vector3d.YAxis, -Vector3d.ZAxis),
                "front" => (Vector3d.XAxis, Vector3d.ZAxis, -Vector3d.YAxis),
                "back" => (-Vector3d.XAxis, Vector3d.ZAxis, Vector3d.YAxis),
                "right" => (Vector3d.YAxis, Vector3d.ZAxis, Vector3d.XAxis),
                "left" => (-Vector3d.YAxis, Vector3d.ZAxis, -Vector3d.XAxis),
                _ => (Vector3d.XAxis, Vector3d.YAxis, Vector3d.ZAxis),
            };
        }

        private static List<Curve> ExtractWireframe(GeometryBase geom)
        {
            var output = new List<Curve>();
            switch (geom)
            {
                case Curve c:
                    output.Add(c);
                    break;
                case Brep b:
                    output.AddRange(b.Edges.Select(e => e.DuplicateCurve()).Where(x => x != null)!);
                    break;
                case Mesh m:
                    var poly = m.GetNakedEdges();
                    if (poly != null)
                        foreach (var pl in poly) output.Add(new PolylineCurve(pl));
                    break;
                case Extrusion ex:
                    output.AddRange(ex.ToBrep().Edges.Select(e => e.DuplicateCurve()).Where(x => x != null)!);
                    break;
            }
            return output;
        }

        private static Curve? ProjectCurve(Curve crv, (Vector3d u, Vector3d v, Vector3d n) basis, Point3d target, double scale)
        {
            var dup = crv.DuplicateCurve();
            if (dup == null) return null;
            var pts = new List<Point3d>();
            int sample = Math.Max(8, (int)Math.Ceiling(dup.GetLength()));
            var dom = dup.Domain;
            for (int i = 0; i <= sample; i++)
            {
                var t = dom.T0 + (dom.T1 - dom.T0) * (i / (double)sample);
                var p = dup.PointAt(t);
                var u = (p - Point3d.Origin) * basis.u;
                var v = (p - Point3d.Origin) * basis.v;
                pts.Add(new Point3d(target.X + u * scale, target.Y + v * scale, target.Z));
            }
            return new PolylineCurve(pts);
        }

        public JObject SectionCut(JObject p)
        {
            var sheetId = p["sheet_id"]!.ToString();
            var meta = ReadSheetMeta(sheetId);
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var origin = ToPoint(p["plane_origin"]!);
            var normal = ToVector(p["plane_normal"]!);
            normal.Unitize();
            var target = ToPoint(p["target_origin"]!);
            var scale = p["viewport_scale"]?.Value<double>() ?? 0.01;
            var plane = new Plane(origin, normal);
            var layerIdx = EnsureLayer(p["layer"]?.ToString() ?? $"Sheets::{meta.name}");

            var newIds = new JArray();
            foreach (var id in ids)
            {
                var brep = FindBrep(id.ToString());
                if (brep == null) continue;
                var crvs = Rhino.Geometry.Intersect.Intersection.BrepPlane(
                    brep, plane, Doc.ModelAbsoluteTolerance, out var section, out _);
                if (!crvs || section == null) continue;
                foreach (var c in section)
                {
                    // Project to sheet target frame using the cut plane axes.
                    var basis = (plane.XAxis, plane.YAxis, plane.ZAxis);
                    var projected = ProjectCurve(c, basis, target, scale);
                    if (projected == null) continue;
                    var attrs = new ObjectAttributes { LayerIndex = layerIdx };
                    attrs.SetUserString("sheet_id", sheetId);
                    attrs.SetUserString("source_object_id", id.ToString());
                    attrs.SetUserString("cut_kind", "section");
                    var nid = Doc.Objects.AddCurve(projected, attrs);
                    newIds.Add(nid.ToString());
                }
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["sheet_id"] = sheetId,
                    ["object_ids"] = newIds,
                    ["plane_origin"] = new JObject { ["x"] = origin.X, ["y"] = origin.Y, ["z"] = origin.Z },
                },
                ["text"] = $"Section cut placed with {newIds.Count} curve(s)",
            };
        }

        public JObject TitleBlockAdd(JObject p)
        {
            var sheetId = p["sheet_id"]!.ToString();
            var meta = ReadSheetMeta(sheetId);
            var project = p["project"]?.ToString() ?? "";
            var title = p["title"]?.ToString() ?? "";
            var scaleText = p["scale_text"]?.ToString() ?? $"1:{meta.scale}";
            var dateIso = p["date_iso"]?.ToString() ?? "";
            var drawnBy = p["drawn_by"]?.ToString() ?? "";
            var sheetNo = p["sheet_no"]?.ToString() ?? "A-001";
            var northAngle = p["north_arrow_angle_deg"]?.Value<double>() ?? 0.0;
            var addNorth = p["add_north_arrow"]?.Value<bool>() ?? true;
            var addScale = p["add_scale_bar"]?.Value<bool>() ?? true;
            var layerIdx = EnsureLayer($"Sheets::{meta.name}");

            var ids = new JArray();
            var tbW = Math.Min(120.0, meta.w * 0.4);
            var tbH = Math.Min(45.0, meta.h * 0.18);
            var tbX = meta.origin.X + meta.w - tbW - 5.0;
            var tbY = meta.origin.Y + 5.0;
            var rect = new Polyline
            {
                new Point3d(tbX, tbY, meta.origin.Z),
                new Point3d(tbX + tbW, tbY, meta.origin.Z),
                new Point3d(tbX + tbW, tbY + tbH, meta.origin.Z),
                new Point3d(tbX, tbY + tbH, meta.origin.Z),
                new Point3d(tbX, tbY, meta.origin.Z),
            };
            var attrs = new ObjectAttributes { LayerIndex = layerIdx, Name = "title_block" };
            ids.Add(Doc.Objects.AddPolyline(rect, attrs).ToString());

            (string label, string value, double x, double y)[] labels =
            {
                ("project", project, tbX + 4.0, tbY + tbH - 6.0),
                ("title", title, tbX + 4.0, tbY + tbH - 14.0),
                ("scale", scaleText, tbX + 4.0, tbY + 12.0),
                ("date", dateIso, tbX + 4.0, tbY + 4.0),
                ("drawn_by", drawnBy, tbX + tbW * 0.5, tbY + 4.0),
                ("sheet_no", sheetNo, tbX + tbW - 30.0, tbY + 4.0),
            };
            foreach (var l in labels)
            {
                if (string.IsNullOrEmpty(l.value)) continue;
                var dot = new TextDot($"{l.label}: {l.value}", new Point3d(l.x, l.y, meta.origin.Z));
                var dotAttrs = new ObjectAttributes { LayerIndex = layerIdx, Name = $"tb_{l.label}" };
                ids.Add(Doc.Objects.AddTextDot(dot, dotAttrs).ToString());
            }

            if (addNorth)
            {
                var nOrigin = new Point3d(meta.origin.X + 25.0, meta.origin.Y + meta.h - 25.0, meta.origin.Z);
                ids.Add(DrawNorthArrow(nOrigin, 20.0, northAngle, layerIdx));
            }
            if (addScale)
            {
                var sOrigin = new Point3d(meta.origin.X + 10.0, meta.origin.Y + 10.0, meta.origin.Z);
                foreach (var sid in DrawScaleBar(sOrigin, 50.0, 5, meta.scale, layerIdx))
                    ids.Add(sid);
            }

            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["sheet_id"] = sheetId,
                    ["object_ids"] = ids,
                },
                ["text"] = $"Title block added to '{meta.name}' ({ids.Count} object(s))",
            };
        }

        private static string DrawNorthArrow(Point3d origin, double size, double angleDeg, int layerIdx)
        {
            var a = (90.0 - angleDeg) * Math.PI / 180.0;
            var tip = new Point3d(origin.X + size * Math.Cos(a), origin.Y + size * Math.Sin(a), origin.Z);
            var sa = (90.0 - angleDeg + 150.0) * Math.PI / 180.0;
            var sb = (90.0 - angleDeg - 150.0) * Math.PI / 180.0;
            var bl = new Point3d(origin.X + size * 0.25 * Math.Cos(sa), origin.Y + size * 0.25 * Math.Sin(sa), origin.Z);
            var br = new Point3d(origin.X + size * 0.25 * Math.Cos(sb), origin.Y + size * 0.25 * Math.Sin(sb), origin.Z);
            var arrow = new Polyline { tip, bl, origin, br, tip };
            var attrs = new ObjectAttributes { LayerIndex = layerIdx, Name = "north_arrow" };
            return Doc.Objects.AddPolyline(arrow, attrs).ToString();
        }

        private static IEnumerable<JToken> DrawScaleBar(Point3d origin, double total, int divisions, int scaleDen, int layerIdx)
        {
            var ids = new List<JToken>();
            var seg = total / divisions;
            var bh = Math.Max(2.0, total * 0.05);
            for (int i = 0; i < divisions; i++)
            {
                var rect = new Polyline
                {
                    new Point3d(origin.X + i * seg, origin.Y, origin.Z),
                    new Point3d(origin.X + (i + 1) * seg, origin.Y, origin.Z),
                    new Point3d(origin.X + (i + 1) * seg, origin.Y + bh, origin.Z),
                    new Point3d(origin.X + i * seg, origin.Y + bh, origin.Z),
                    new Point3d(origin.X + i * seg, origin.Y, origin.Z),
                };
                var a = new ObjectAttributes { LayerIndex = layerIdx, Name = $"scale_bar_{i}" };
                ids.Add(Doc.Objects.AddPolyline(rect, a).ToString());
            }
            var realM = (total / 1000.0) * scaleDen;
            var label = new TextDot($"0 .. {realM:F1} m  (1:{scaleDen})", new Point3d(origin.X, origin.Y - bh, origin.Z));
            var la = new ObjectAttributes { LayerIndex = layerIdx, Name = "scale_bar_label" };
            ids.Add(Doc.Objects.AddTextDot(label, la).ToString());
            return ids;
        }

        public JObject ExportPdf(JObject p)
        {
            var sheetId = p["sheet_id"]!.ToString();
            var meta = ReadSheetMeta(sheetId);
            var path = p["path"]!.ToString();
            var dpi = p["dpi"]?.Value<int>() ?? 300;

            // PDF export: invoke Rhino's _-Print command. The exact PDF
            // arguments depend on user preferences and Rhino version, so we
            // route through a script line that requests a PDF target. Users
            // who need pixel-perfect control should use Rhino's UI directly.
            SafeRunScript(
                $"_-Print _Setup _Destination _PDF _Enter _Resolution {dpi} _Enter _Save \"{path}\" _Enter _Enter",
                "ExportPdf");
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["sheet_id"] = sheetId,
                    ["path"] = path,
                    ["dpi"] = dpi,
                },
                ["text"] = $"Sheet '{meta.name}' exported to {path}",
            };
        }
    }
}

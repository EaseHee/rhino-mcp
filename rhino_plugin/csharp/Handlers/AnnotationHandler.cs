using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
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
            SafeRunScript("_DimLinear");
            return StatusOk("DimLinear command invoked");
        }

        public JObject DimAligned(JObject p)
        {
            SafeRunScript("_DimAligned");
            return StatusOk("DimAligned command invoked");
        }

        public JObject DimAngular(JObject p)
        {
            SafeRunScript("_DimAngle");
            return StatusOk("DimAngular command invoked");
        }

        public JObject Leader(JObject p)
        {
            SafeRunScript("_Leader");
            return StatusOk("Leader command invoked");
        }

        public JObject Hatch(JObject p)
        {
            SafeRunScript("_Hatch");
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

        // ---------------- v0.3 drawing-set markup ----------------

        public JObject NorthArrow(JObject p)
        {
            var origin = ToPoint(p["location"]!);
            double size = p["size"]?.Value<double>() ?? 20.0;
            double angleDeg = p["angle_deg"]?.Value<double>() ?? 0.0;
            string style = p["style"]?.ToString() ?? "simple";
            int layerIdx = AnnotationLayer(p);
            var ids = new JArray();
            if (style == "compass")
            {
                foreach (var off in new[] { 0, 90, 180, 270 })
                {
                    var a = (90.0 - angleDeg + off) * Math.PI / 180.0;
                    var tip = new Point3d(origin.X + size * Math.Cos(a), origin.Y + size * Math.Sin(a), origin.Z);
                    var poly = new Polyline { origin, tip };
                    var attr = new ObjectAttributes { LayerIndex = layerIdx, Name = $"compass_{off}" };
                    ids.Add(Doc.Objects.AddPolyline(poly, attr).ToString());
                }
            }
            else
            {
                var a = (90.0 - angleDeg) * Math.PI / 180.0;
                var tip = new Point3d(origin.X + size * Math.Cos(a), origin.Y + size * Math.Sin(a), origin.Z);
                var sa = (90.0 - angleDeg + 150.0) * Math.PI / 180.0;
                var sb = (90.0 - angleDeg - 150.0) * Math.PI / 180.0;
                var bl = new Point3d(origin.X + size * 0.25 * Math.Cos(sa), origin.Y + size * 0.25 * Math.Sin(sa), origin.Z);
                var br = new Point3d(origin.X + size * 0.25 * Math.Cos(sb), origin.Y + size * 0.25 * Math.Sin(sb), origin.Z);
                var poly = new Polyline { tip, bl, origin, br, tip };
                var attr = new ObjectAttributes { LayerIndex = layerIdx, Name = "north_arrow" };
                ids.Add(Doc.Objects.AddPolyline(poly, attr).ToString());
            }
            var labelDot = new TextDot("N", new Point3d(origin.X, origin.Y - size * 0.4, origin.Z));
            var la = new ObjectAttributes { LayerIndex = layerIdx, Name = "north_arrow_label" };
            ids.Add(Doc.Objects.AddTextDot(labelDot, la).ToString());
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_ids"] = ids, ["style"] = style, ["angle_deg"] = angleDeg, ["size"] = size },
                ["text"] = $"North arrow placed ({style})",
            };
        }

        public JObject ScaleBar(JObject p)
        {
            var origin = ToPoint(p["location"]!);
            double total = p["total_length"]?.Value<double>() ?? 50.0;
            int divisions = p["divisions"]?.Value<int>() ?? 5;
            int scaleDen = p["scale_denominator"]?.Value<int>() ?? 100;
            int layerIdx = AnnotationLayer(p);
            double seg = total / divisions;
            double bh = Math.Max(2.0, total * 0.05);
            var ids = new JArray();
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
                var attr = new ObjectAttributes { LayerIndex = layerIdx, Name = $"scale_bar_{i}" };
                ids.Add(Doc.Objects.AddPolyline(rect, attr).ToString());
            }
            double realM = (total / 1000.0) * scaleDen;
            var lbl = new TextDot($"0 .. {realM:F1} m  (1:{scaleDen})", new Point3d(origin.X, origin.Y - bh, origin.Z));
            var la = new ObjectAttributes { LayerIndex = layerIdx, Name = "scale_bar_label" };
            ids.Add(Doc.Objects.AddTextDot(lbl, la).ToString());
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_ids"] = ids, ["divisions"] = divisions, ["scale_denominator"] = scaleDen },
                ["text"] = $"Scale bar placed ({divisions} divisions @1:{scaleDen})",
            };
        }

        public JObject RevisionCloud(JObject p)
        {
            var pts = (p["boundary_points"] as JArray)!.Select(ToPoint).ToList();
            string revNo = p["revision_no"]?.ToString() ?? "R1";
            string dateIso = p["date_iso"]?.ToString() ?? "";
            int bumpCount = p["bump_count"]?.Value<int>() ?? 24;
            double bumpRadius = p["bump_radius"]?.Value<double>() ?? 1.5;
            int layerIdx = AnnotationLayer(p);

            if (pts.Count < 3) throw new ArgumentException("boundary_points needs at least 3 points");
            if (pts[0].DistanceTo(pts[^1]) > 1e-6) pts.Add(pts[0]);
            int perSeg = Math.Max(1, bumpCount / (pts.Count - 1));
            var cloud = new Polyline();
            for (int i = 0; i < pts.Count - 1; i++)
            {
                var a = pts[i]; var b = pts[i + 1];
                for (int k = 0; k < perSeg; k++)
                {
                    double tt = k / (double)perSeg;
                    var basePt = new Point3d(a.X * (1 - tt) + b.X * tt, a.Y * (1 - tt) + b.Y * tt, a.Z * (1 - tt) + b.Z * tt);
                    double dx = b.X - a.X, dy = b.Y - a.Y;
                    double ln = Math.Sqrt(dx * dx + dy * dy);
                    if (ln < 1e-9) ln = 1.0;
                    double nx = -dy / ln, ny = dx / ln;
                    var bump = new Point3d(basePt.X + nx * bumpRadius, basePt.Y + ny * bumpRadius, basePt.Z);
                    cloud.Add(basePt);
                    cloud.Add(bump);
                }
            }
            cloud.Add(pts[0]);
            var attr = new ObjectAttributes { LayerIndex = layerIdx, Name = $"revision_{revNo}" };
            var cloudId = Doc.Objects.AddPolyline(cloud, attr);
            double cx = pts.Average(pt => pt.X), cy = pts.Average(pt => pt.Y), cz = pts.Average(pt => pt.Z);
            var label = $"Rev {revNo}" + (string.IsNullOrEmpty(dateIso) ? "" : $"  {dateIso}");
            var dot = new TextDot(label, new Point3d(cx, cy, cz));
            var la = new ObjectAttributes { LayerIndex = layerIdx, Name = $"revision_label_{revNo}" };
            var dotId = Doc.Objects.AddTextDot(dot, la);
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_ids"] = new JArray(cloudId.ToString(), dotId.ToString()),
                    ["revision_no"] = revNo,
                },
                ["text"] = $"Revision cloud {revNo} placed",
            };
        }

        public JObject Callout(JObject p)
        {
            var target = ToPoint(p["target_point"]!);
            var origin = ToPoint(p["leader_origin"]!);
            string text = p["text"]!.ToString();
            string style = p["style"]?.ToString() ?? "balloon";
            int layerIdx = AnnotationLayer(p);
            var ids = new JArray();
            var leader = new Polyline { target, origin };
            ids.Add(Doc.Objects.AddPolyline(leader, new ObjectAttributes { LayerIndex = layerIdx, Name = "callout_leader" }).ToString());
            if (style == "box")
            {
                double tw = Math.Max(text.Length * 1.5, 6.0);
                double th = 4.0;
                var box = new Polyline
                {
                    origin,
                    new Point3d(origin.X + tw, origin.Y, origin.Z),
                    new Point3d(origin.X + tw, origin.Y + th, origin.Z),
                    new Point3d(origin.X, origin.Y + th, origin.Z),
                    origin,
                };
                ids.Add(Doc.Objects.AddPolyline(box, new ObjectAttributes { LayerIndex = layerIdx, Name = "callout_box" }).ToString());
            }
            else
            {
                var circle = new Circle(origin, 4.0);
                ids.Add(Doc.Objects.AddCircle(circle, new ObjectAttributes { LayerIndex = layerIdx, Name = "callout_balloon" }).ToString());
            }
            var dot = new TextDot(text, origin);
            ids.Add(Doc.Objects.AddTextDot(dot, new ObjectAttributes { LayerIndex = layerIdx, Name = "callout_text" }).ToString());
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_ids"] = ids, ["style"] = style, ["text"] = text },
                ["text"] = $"Callout placed ({style})",
            };
        }

        public JObject DimStyleCreate(JObject p)
        {
            var name = p["name"]!.ToString();
            double textHeight = p["text_height"]?.Value<double>() ?? 2.5;
            double arrowSize = p["arrow_size"]?.Value<double>() ?? 2.0;
            string font = p["font"]?.ToString() ?? "Arial";
            var ds = new Rhino.DocObjects.DimensionStyle
            {
                Name = name,
                Font = Rhino.DocObjects.Font.FromQuartetProperties(font, false, false),
                TextHeight = textHeight,
                ArrowLength = arrowSize,
            };
            int idx = Doc.DimStyles.Add(ds, false);
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["index"] = idx, ["name"] = name },
                ["text"] = $"Dimension style '{name}' created at index {idx}",
            };
        }

        private static int AnnotationLayer(JObject p)
        {
            var name = p["layer"]?.ToString();
            if (string.IsNullOrEmpty(name)) return Doc.Layers.CurrentLayerIndex;
            var idx = Doc.Layers.FindByFullPath(name, -1);
            if (idx >= 0) return idx;
            return Doc.Layers.Add(new Layer { Name = name });
        }
    }
}

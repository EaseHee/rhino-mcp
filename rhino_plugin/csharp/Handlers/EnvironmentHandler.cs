using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;
using Rhino.Geometry.Intersect;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Environmental analysis — solar position, sun path, shadow projection,
    /// solar exposure ray casting. Solar position uses the same NOAA SPA
    /// approximation as the Python side so results are consistent across modes.
    /// </summary>
    public class EnvironmentHandler : HandlerBase
    {
        private static (double az, double alt) SolarPosition(double latitude, double longitude, DateTime localTime, double tzOffsetH)
        {
            var utc = localTime.AddHours(-tzOffsetH);
            var j2000 = new DateTime(2000, 1, 1, 12, 0, 0, DateTimeKind.Unspecified);
            var n = (utc - j2000).TotalSeconds / 86400.0;
            var L = (280.460 + 0.9856474 * n) % 360.0;
            if (L < 0) L += 360.0;
            var g = ((357.528 + 0.9856003 * n) % 360.0) * Math.PI / 180.0;
            if (g < 0) g += 2 * Math.PI;
            var lam = (L + 1.915 * Math.Sin(g) + 0.020 * Math.Sin(2 * g)) * Math.PI / 180.0;
            var eps = (23.439 - 0.0000004 * n) * Math.PI / 180.0;
            var ra = Math.Atan2(Math.Cos(eps) * Math.Sin(lam), Math.Cos(lam));
            var dec = Math.Asin(Math.Sin(eps) * Math.Sin(lam));
            var gmst = (18.697374558 + 24.06570982441908 * n) % 24.0;
            if (gmst < 0) gmst += 24.0;
            var lst = ((gmst * 15.0 + longitude) % 360.0) * Math.PI / 180.0;
            var ha = lst - ra;
            var latR = latitude * Math.PI / 180.0;
            var sinAlt = Math.Sin(latR) * Math.Sin(dec) + Math.Cos(latR) * Math.Cos(dec) * Math.Cos(ha);
            sinAlt = Math.Max(-1.0, Math.Min(1.0, sinAlt));
            var alt = Math.Asin(sinAlt) * 180.0 / Math.PI;
            var sinAz = -Math.Cos(dec) * Math.Sin(ha);
            var cosAz = Math.Sin(dec) * Math.Cos(latR) - Math.Cos(dec) * Math.Sin(latR) * Math.Cos(ha);
            var az = (Math.Atan2(sinAz, cosAz) * 180.0 / Math.PI + 360.0) % 360.0;
            return (az, alt);
        }

        private static Vector3d SunVector(double azDeg, double altDeg)
        {
            var az = azDeg * Math.PI / 180.0;
            var alt = altDeg * Math.PI / 180.0;
            return new Vector3d(Math.Cos(alt) * Math.Sin(az), Math.Cos(alt) * Math.Cos(az), Math.Sin(alt));
        }

        public JObject SunPosition(JObject p)
        {
            var lat = p["latitude"]?.Value<double>() ?? 37.5663;
            var lon = p["longitude"]?.Value<double>() ?? 126.9779;
            var iso = p["datetime_iso"]!.ToString();
            var tz = p["timezone_offset_h"]?.Value<double>() ?? 9.0;
            var when = DateTime.Parse(iso);
            var (az, alt) = SolarPosition(lat, lon, when, tz);
            var v = SunVector(az, alt);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["azimuth_deg"] = Math.Round(az, 4),
                    ["altitude_deg"] = Math.Round(alt, 4),
                    ["sun_vector"] = new JObject { ["x"] = Math.Round(v.X, 6), ["y"] = Math.Round(v.Y, 6), ["z"] = Math.Round(v.Z, 6) },
                    ["is_above_horizon"] = alt > 0,
                    ["datetime"] = iso,
                    ["latitude"] = lat,
                    ["longitude"] = lon,
                },
                ["text"] = $"Sun: az={az:F2} deg, alt={alt:F2} deg",
            };
        }

        public JObject SunPath(JObject p)
        {
            var lat = p["latitude"]?.Value<double>() ?? 37.5663;
            var lon = p["longitude"]?.Value<double>() ?? 126.9779;
            var year = p["year"]?.Value<int>() ?? 2026;
            var months = (p["months"] as JArray)?.Select(t => t.Value<int>()).ToList() ?? new List<int> { 3, 6, 9, 12 };
            var hours = (p["hours"] as JArray)?.Select(t => t.Value<int>()).ToList() ?? new List<int> { 6, 9, 12, 15, 18 };
            var radius = p["radius"]?.Value<double>() ?? 100.0;
            var center = p["center_point"] != null ? ToPoint(p["center_point"]!) : Point3d.Origin;
            var tz = p["timezone_offset_h"]?.Value<double>() ?? 9.0;
            var layerName = p["layer"]?.ToString() ?? "Site::SunPath";
            var idx = Doc.Layers.FindByFullPath(layerName, -1);
            if (idx < 0) idx = Doc.Layers.Add(new Layer { Name = layerName });

            var ids = new JArray();
            int sampleCount = 0;
            foreach (var month in months)
            {
                var poly = new Polyline();
                foreach (var hour in hours)
                {
                    var when = new DateTime(year, month, 21, hour, 0, 0);
                    var (az, alt) = SolarPosition(lat, lon, when, tz);
                    if (alt < 0) continue;
                    var v = SunVector(az, alt);
                    poly.Add(center.X + radius * v.X, center.Y + radius * v.Y, center.Z + radius * v.Z);
                    sampleCount++;
                }
                if (poly.Count >= 2)
                {
                    var attrs = new ObjectAttributes { LayerIndex = idx, Name = $"sunpath_{year}_{month:00}" };
                    attrs.SetUserString("month", month.ToString());
                    ids.Add(Doc.Objects.AddPolyline(poly, attrs).ToString());
                }
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["polyline_ids"] = ids,
                    ["month_count"] = ids.Count,
                    ["sample_count"] = sampleCount,
                    ["radius"] = radius,
                },
                ["text"] = $"Sun path: {ids.Count} polyline(s), {sampleCount} samples",
            };
        }

        public JObject ShadowProject(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => t.ToString()).ToList();
            var sun = ToVector(p["sun_vector"]!);
            sun.Unitize();
            var groundZ = p["ground_z"]?.Value<double>() ?? 0.0;
            var layerName = p["layer"]?.ToString() ?? "Site::Shadows";
            var idx = Doc.Layers.FindByFullPath(layerName, -1);
            if (idx < 0) idx = Doc.Layers.Add(new Layer { Name = layerName });

            var newIds = new JArray();
            foreach (var idStr in ids)
            {
                var obj = FindObject(idStr) ?? throw new KeyNotFoundException($"object not found: {idStr}");
                // Build a wireframe and project each vertex onto Z=ground_z along sun.
                var hullSrc = new List<Point3d>();
                foreach (var crv in WireframeOf(obj.Geometry))
                {
                    var dom = crv.Domain;
                    int sample = 16;
                    for (int i = 0; i <= sample; i++)
                    {
                        var t = dom.T0 + (dom.T1 - dom.T0) * (i / (double)sample);
                        var pt = crv.PointAt(t);
                        var projected = ProjectToZ(pt, sun, groundZ);
                        if (projected.HasValue) hullSrc.Add(projected.Value);
                    }
                }
                if (hullSrc.Count < 3) continue;
                var hull = ConvexHullXY(hullSrc, groundZ);
                if (hull.Count < 3) continue;
                hull.Add(hull[0]);
                var attrs = new ObjectAttributes { LayerIndex = idx, Name = $"shadow_{idStr.Substring(0, 8)}" };
                attrs.SetUserString("source_object_id", idStr);
                newIds.Add(Doc.Objects.AddPolyline(hull, attrs).ToString());
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["shadow_ids"] = newIds,
                    ["object_count"] = ids.Count,
                    ["shadow_count"] = newIds.Count,
                    ["ground_z"] = groundZ,
                },
                ["text"] = $"Projected {newIds.Count} shadow(s) from {ids.Count} object(s)",
            };
        }

        public JObject SolarExposureEstimate(JObject p)
        {
            var targetId = p["target_object_id"]!.ToString();
            var lat = p["latitude"]?.Value<double>() ?? 37.5663;
            var lon = p["longitude"]?.Value<double>() ?? 126.9779;
            var dateIso = p["date_iso"]!.ToString();
            var hourRange = p["hour_range"] as JArray;
            int hStart = hourRange != null ? hourRange[0].Value<int>() : 8;
            int hEnd = hourRange != null ? hourRange[1].Value<int>() : 18;
            int stepMin = p["step_minutes"]?.Value<int>() ?? 60;
            var tz = p["timezone_offset_h"]?.Value<double>() ?? 9.0;
            var obstrIds = (p["obstruction_object_ids"] as JArray)?.Select(t => t.ToString()).ToList() ?? new List<string>();

            var target = FindObject(targetId) ?? throw new KeyNotFoundException($"target not found: {targetId}");
            var origin = target.Geometry.GetBoundingBox(true).Center;
            origin.Z += 0.1;  // lift slightly to avoid self-intersection

            var obstructions = obstrIds
                .Select(FindBrep)
                .Where(b => b != null)
                .Cast<Brep>()
                .ToList();

            int total = 0, lit = 0;
            DateTime baseDate = DateTime.Parse(dateIso);
            for (int hour = hStart; hour <= hEnd; hour++)
            {
                for (int min = 0; min < 60; min += stepMin)
                {
                    var when = baseDate.AddHours(hour).AddMinutes(min);
                    var (az, alt) = SolarPosition(lat, lon, when, tz);
                    if (alt <= 0) { total++; continue; }
                    total++;
                    var v = SunVector(az, alt);
                    var ray = new Ray3d(origin, v);
                    bool blocked = false;
                    foreach (var b in obstructions)
                    {
                        var hits = Intersection.RayShoot(ray, new[] { b }, 1);
                        if (hits != null && hits.Length > 0) { blocked = true; break; }
                    }
                    if (!blocked) lit++;
                }
            }
            double ratio = total > 0 ? (double)lit / total : 0.0;
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["target_object_id"] = targetId,
                    ["lit_samples"] = lit,
                    ["total_samples"] = total,
                    ["exposure_ratio"] = Math.Round(ratio, 4),
                    ["date"] = dateIso,
                },
                ["text"] = $"Exposure ratio {ratio * 100:F1}% on {targetId}",
            };
        }

        private static IEnumerable<Curve> WireframeOf(GeometryBase geom)
        {
            switch (geom)
            {
                case Curve c:
                    yield return c;
                    break;
                case Brep b:
                    foreach (var e in b.Edges)
                    {
                        var dup = e.DuplicateCurve();
                        if (dup != null) yield return dup;
                    }
                    break;
                case Mesh m:
                    var nakedEdges = m.GetNakedEdges();
                    if (nakedEdges != null)
                        foreach (var pl in nakedEdges) yield return new PolylineCurve(pl);
                    break;
                case Extrusion ex:
                    foreach (var e in ex.ToBrep().Edges)
                    {
                        var dup = e.DuplicateCurve();
                        if (dup != null) yield return dup;
                    }
                    break;
            }
        }

        private static Point3d? ProjectToZ(Point3d p, Vector3d sunDir, double z)
        {
            if (Math.Abs(sunDir.Z) < 1e-9) return null;
            var t = (z - p.Z) / -sunDir.Z;
            if (t <= 0) return null;
            return new Point3d(p.X - t * sunDir.X, p.Y - t * sunDir.Y, z);
        }

        private static List<Point3d> ConvexHullXY(List<Point3d> pts, double z)
        {
            var sorted = pts.Select(p => (X: Math.Round(p.X, 6), Y: Math.Round(p.Y, 6)))
                .Distinct()
                .OrderBy(p => p.X).ThenBy(p => p.Y)
                .ToList();
            if (sorted.Count <= 1)
                return sorted.Select(s => new Point3d(s.X, s.Y, z)).ToList();
            double Cross((double X, double Y) o, (double X, double Y) a, (double X, double Y) b)
                => (a.X - o.X) * (b.Y - o.Y) - (a.Y - o.Y) * (b.X - o.X);

            var lower = new List<(double X, double Y)>();
            foreach (var p in sorted)
            {
                while (lower.Count >= 2 && Cross(lower[^2], lower[^1], p) <= 0) lower.RemoveAt(lower.Count - 1);
                lower.Add(p);
            }
            var upper = new List<(double X, double Y)>();
            for (int i = sorted.Count - 1; i >= 0; i--)
            {
                var p = sorted[i];
                while (upper.Count >= 2 && Cross(upper[^2], upper[^1], p) <= 0) upper.RemoveAt(upper.Count - 1);
                upper.Add(p);
            }
            lower.RemoveAt(lower.Count - 1);
            upper.RemoveAt(upper.Count - 1);
            return lower.Concat(upper).Select(s => new Point3d(s.X, s.Y, z)).ToList();
        }
    }
}

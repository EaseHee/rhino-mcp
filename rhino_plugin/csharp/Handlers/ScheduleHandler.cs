using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMCPBridge.Handlers
{
    /// <summary>
    /// Quantity / schedule aggregation — per layer / per material / per user_text.
    /// Brep area + volume use ``AreaMassProperties`` / ``VolumeMassProperties`` for
    /// accurate measurement; mesh and curve fall back to lightweight calculation.
    /// </summary>
    public class ScheduleHandler : HandlerBase
    {
        private static double SafeArea(GeometryBase geom)
        {
            switch (geom)
            {
                case Brep b:
                    var amp = AreaMassProperties.Compute(b);
                    return amp?.Area ?? 0.0;
                case Surface s:
                    var amps = AreaMassProperties.Compute(s);
                    return amps?.Area ?? 0.0;
                case Mesh m:
                    var amm = AreaMassProperties.Compute(m);
                    return amm?.Area ?? 0.0;
                default:
                    return 0.0;
            }
        }

        private static double SafeVolume(GeometryBase geom)
        {
            switch (geom)
            {
                case Brep b when b.IsSolid:
                    var vmp = VolumeMassProperties.Compute(b);
                    return vmp?.Volume ?? 0.0;
                case Mesh m when m.IsClosed:
                    var vmm = VolumeMassProperties.Compute(m);
                    return vmm?.Volume ?? 0.0;
                default:
                    return 0.0;
            }
        }

        private static double SafeLength(GeometryBase geom)
        {
            return geom is Curve c ? c.GetLength() : 0.0;
        }

        private static void Accumulate(JObject row, GeometryBase geom, IEnumerable<string> fields)
        {
            foreach (var f in fields)
            {
                switch (f)
                {
                    case "count":
                        row["count"] = (row["count"]?.Value<int>() ?? 0) + 1;
                        break;
                    case "area":
                        row["area"] = Math.Round((row["area"]?.Value<double>() ?? 0.0) + SafeArea(geom), 6);
                        break;
                    case "volume":
                        row["volume"] = Math.Round((row["volume"]?.Value<double>() ?? 0.0) + SafeVolume(geom), 6);
                        break;
                    case "length":
                        row["length"] = Math.Round((row["length"]?.Value<double>() ?? 0.0) + SafeLength(geom), 6);
                        break;
                }
            }
        }

        private static List<string> Fields(JObject p)
        {
            var arr = p["fields"] as JArray;
            return arr?.Select(t => t.ToString()).ToList() ?? new List<string> { "count", "area", "volume" };
        }

        public JObject ByLayer(JObject p)
        {
            var fields = Fields(p);
            var includeSub = p["include_sublayers"]?.Value<bool>() ?? true;
            var filterArr = p["layer_filter"] as JArray;
            var filters = filterArr?.Select(t => t.ToString()).ToList();
            var rowsByLayer = new Dictionary<string, JObject>();
            foreach (var obj in Doc.Objects)
            {
                if (obj.IsDeleted) continue;
                var layer = Doc.Layers.FindIndex(obj.Attributes.LayerIndex);
                if (layer == null) continue;
                var path = layer.FullPath;
                if (filters != null && filters.Count > 0)
                {
                    var ok = filters.Any(f => path == f || (includeSub && path.StartsWith(f + "::")));
                    if (!ok) continue;
                }
                if (!rowsByLayer.TryGetValue(path, out var row))
                {
                    row = new JObject { ["layer"] = path };
                    rowsByLayer[path] = row;
                }
                Accumulate(row, obj.Geometry, fields);
            }
            return BuildScheduleResult(rowsByLayer.Values.OrderBy(r => r["layer"]?.ToString()).ToList(), fields, "by_layer");
        }

        public JObject ByUserText(JObject p)
        {
            var key = p["group_key"]!.ToString();
            var valueFilter = p["value_filter"]?.Type == JTokenType.Null ? null : p["value_filter"]?.ToString();
            var fields = Fields(p);
            var rowsByValue = new Dictionary<string, JObject>();
            foreach (var obj in Doc.Objects)
            {
                if (obj.IsDeleted) continue;
                var v = obj.Attributes.GetUserString(key);
                if (string.IsNullOrEmpty(v)) continue;
                if (valueFilter != null && v != valueFilter) continue;
                if (!rowsByValue.TryGetValue(v, out var row))
                {
                    row = new JObject { [key] = v };
                    rowsByValue[v] = row;
                }
                Accumulate(row, obj.Geometry, fields);
            }
            return BuildScheduleResult(rowsByValue.Values.OrderBy(r => r[key]?.ToString()).ToList(), fields, $"by_user_text({key})");
        }

        public JObject ByMaterial(JObject p)
        {
            var fields = Fields(p);
            var rowsByMat = new Dictionary<string, JObject>();
            foreach (var obj in Doc.Objects)
            {
                if (obj.IsDeleted) continue;
                var matIdx = obj.Attributes.MaterialIndex;
                var name = matIdx >= 0 && matIdx < Doc.Materials.Count
                    ? (Doc.Materials[matIdx].Name ?? $"Material_{matIdx}")
                    : "Default";
                if (!rowsByMat.TryGetValue(name, out var row))
                {
                    row = new JObject { ["material"] = name };
                    rowsByMat[name] = row;
                }
                Accumulate(row, obj.Geometry, fields);
            }
            return BuildScheduleResult(rowsByMat.Values.OrderBy(r => r["material"]?.ToString()).ToList(), fields, "by_material");
        }

        public JObject ObjectQuantity(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => t.ToString()).ToList();
            var fields = (p["fields"] as JArray)?.Select(t => t.ToString()).ToList()
                ?? new List<string> { "area", "volume", "length", "centroid", "bbox" };
            var rows = new JArray();
            foreach (var idStr in ids)
            {
                var obj = FindObject(idStr) ?? throw new KeyNotFoundException($"object not found: {idStr}");
                var geom = obj.Geometry;
                var entry = new JObject
                {
                    ["object_id"] = idStr,
                    ["kind"] = geom.GetType().Name,
                };
                if (fields.Contains("area")) entry["area"] = Math.Round(SafeArea(geom), 6);
                if (fields.Contains("volume")) entry["volume"] = Math.Round(SafeVolume(geom), 6);
                if (fields.Contains("length")) entry["length"] = Math.Round(SafeLength(geom), 6);
                if (fields.Contains("centroid"))
                {
                    var bb = geom.GetBoundingBox(true);
                    var c = bb.Center;
                    entry["centroid"] = new JObject { ["x"] = c.X, ["y"] = c.Y, ["z"] = c.Z };
                }
                if (fields.Contains("bbox"))
                {
                    var bb = geom.GetBoundingBox(true);
                    entry["bbox"] = new JObject
                    {
                        ["min"] = new JObject { ["x"] = bb.Min.X, ["y"] = bb.Min.Y, ["z"] = bb.Min.Z },
                        ["max"] = new JObject { ["x"] = bb.Max.X, ["y"] = bb.Max.Y, ["z"] = bb.Max.Z },
                    };
                }
                rows.Add(entry);
            }
            return new JObject
            {
                ["summary"] = new JObject { ["rows"] = rows, ["row_count"] = rows.Count },
                ["text"] = $"Object quantities: {rows.Count} row(s)",
            };
        }

        private static JObject BuildScheduleResult(List<JObject> rows, List<string> fields, string label)
        {
            var arr = new JArray(rows.Cast<JToken>().ToArray());
            var totals = new JObject();
            foreach (var f in fields)
            {
                if (f == "count")
                {
                    totals[f] = rows.Sum(r => r[f]?.Value<int>() ?? 0);
                }
                else
                {
                    totals[f] = Math.Round(rows.Sum(r => r[f]?.Value<double>() ?? 0.0), 6);
                }
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["rows"] = arr,
                    ["totals"] = totals,
                    ["row_count"] = rows.Count,
                    ["fields"] = new JArray(fields.Cast<object>().ToArray()),
                },
                ["text"] = $"Schedule {label}: {rows.Count} row(s)",
            };
        }
    }
}

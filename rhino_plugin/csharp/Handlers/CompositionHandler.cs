using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Scene-composition tools — high-level multi-object placement that the
    /// LLM otherwise has to drive call-by-call.
    /// </summary>
    public class CompositionHandler : HandlerBase
    {
        public JObject PlaceGrid(JObject p)
        {
            var sourceId = p["source_object_id"]!.ToString();
            var src = FindObject(sourceId)
                ?? throw new InvalidOperationException($"object not found: {sourceId}");
            var basePt = ToPoint(p["base_point"]!);
            var countX = p["count_x"]!.Value<int>();
            var countY = p["count_y"]!.Value<int>();
            var spacingX = p["spacing_x"]!.Value<double>();
            var spacingY = p["spacing_y"]!.Value<double>();
            var skipOrigin = p["skip_origin"]?.Value<bool>() ?? true;
            var prefix = p["name_prefix"]?.ToString();

            var newIds = new JArray();
            for (int ix = 0; ix < countX; ix++)
            {
                for (int iy = 0; iy < countY; iy++)
                {
                    if (ix == 0 && iy == 0 && skipOrigin) continue;
                    var offset = new Vector3d(
                        basePt.X + ix * spacingX,
                        basePt.Y + iy * spacingY,
                        basePt.Z);
                    var xform = Transform.Translation(offset);
                    var dup = src.Geometry.Duplicate();
                    dup.Transform(xform);
                    var attrs = src.Attributes.Duplicate();
                    if (!string.IsNullOrEmpty(prefix))
                        attrs.Name = $"{prefix}_{ix}_{iy}";
                    var id = Doc.Objects.Add(dup, attrs);
                    newIds.Add(id.ToString());
                }
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["source_object_id"] = sourceId,
                    ["object_ids"] = newIds,
                    ["count_x"] = countX,
                    ["count_y"] = countY,
                },
                ["text"] = $"Grid placed {newIds.Count} copies ({countX}x{countY})",
            };
        }

        public JObject StackFloors(JObject p)
        {
            var sourceId = p["source_object_id"]!.ToString();
            var src = FindObject(sourceId)
                ?? throw new InvalidOperationException($"object not found: {sourceId}");
            var floorCount = p["floor_count"]!.Value<int>();
            var floorHeight = p["floor_height"]!.Value<double>();
            var prefix = p["name_prefix"]?.ToString();

            var newIds = new JArray();
            for (int k = 1; k <= floorCount; k++)
            {
                var xform = Transform.Translation(new Vector3d(0, 0, k * floorHeight));
                var dup = src.Geometry.Duplicate();
                dup.Transform(xform);
                var attrs = src.Attributes.Duplicate();
                if (!string.IsNullOrEmpty(prefix))
                    attrs.Name = $"{prefix}_F{k}";
                var id = Doc.Objects.Add(dup, attrs);
                newIds.Add(id.ToString());
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["source_object_id"] = sourceId,
                    ["object_ids"] = newIds,
                    ["floor_count"] = floorCount,
                },
                ["text"] = $"Stacked {newIds.Count} floor copies",
            };
        }

        public JObject Scatter(JObject p)
        {
            var sourceId = p["source_object_id"]!.ToString();
            var src = FindObject(sourceId)
                ?? throw new InvalidOperationException($"object not found: {sourceId}");
            var bMin = ToPoint(p["boundary_min"]!);
            var bMax = ToPoint(p["boundary_max"]!);
            if (bMax.X <= bMin.X || bMax.Y <= bMin.Y)
                throw new ArgumentException("boundary_max must be > boundary_min on X and Y");
            var count = p["count"]!.Value<int>();
            var seed = p["seed"]?.Type != JTokenType.Null ? p["seed"]?.Value<int?>() : null;
            var jitter = p["rotation_jitter_deg"]?.Value<double>() ?? 0.0;
            var rng = seed.HasValue ? new Random(seed.Value) : new Random();

            var newIds = new JArray();
            for (int i = 0; i < count; i++)
            {
                double x = bMin.X + rng.NextDouble() * (bMax.X - bMin.X);
                double y = bMin.Y + rng.NextDouble() * (bMax.Y - bMin.Y);
                double z = bMin.Z;
                var translate = Transform.Translation(new Vector3d(x, y, z));
                var xform = translate;
                if (jitter > 0)
                {
                    double angle = (rng.NextDouble() * 2 - 1) * RhinoMath.ToRadians(jitter);
                    var rot = Transform.Rotation(angle, Vector3d.ZAxis, new Point3d(x, y, z));
                    xform = rot * translate;
                }
                var dup = src.Geometry.Duplicate();
                dup.Transform(xform);
                var id = Doc.Objects.Add(dup, src.Attributes.Duplicate());
                newIds.Add(id.ToString());
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["source_object_id"] = sourceId,
                    ["object_ids"] = newIds,
                    ["count"] = count,
                    ["seed"] = seed.HasValue ? (JToken)seed.Value : JValue.CreateNull(),
                },
                ["text"] = $"Scattered {newIds.Count} copies",
            };
        }

        public JObject ReplicateAlongCurve(JObject p)
        {
            var sourceId = p["source_object_id"]!.ToString();
            var src = FindObject(sourceId)
                ?? throw new InvalidOperationException($"object not found: {sourceId}");
            var crv = FindCurve(p["curve_id"]!.ToString())
                ?? throw new ArgumentException("curve_id must reference a curve");
            var count = p["count"]!.Value<int>();
            var align = p["align_to_tangent"]?.Value<bool>() ?? true;
            var includeEndpoints = p["include_endpoints"]?.Value<bool>() ?? true;

            var dom = crv.Domain;
            var newIds = new JArray();
            for (int k = 0; k < count; k++)
            {
                double t;
                if (count == 1) t = 0.5 * (dom.T0 + dom.T1);
                else if (includeEndpoints) t = dom.T0 + (dom.T1 - dom.T0) * (k / (double)(count - 1));
                else t = dom.T0 + (dom.T1 - dom.T0) * ((k + 1) / (double)(count + 1));
                var pt = crv.PointAt(t);
                Transform xform;
                if (align)
                {
                    var tangent = crv.TangentAt(t);
                    var z = Vector3d.ZAxis;
                    var x = tangent;
                    x.Unitize();
                    var y = Vector3d.CrossProduct(z, x);
                    if (y.Length < 1e-9) y = Vector3d.YAxis;
                    y.Unitize();
                    var dst = new Plane(pt, x, y);
                    xform = Transform.PlaneToPlane(Plane.WorldXY, dst);
                }
                else
                {
                    xform = Transform.Translation(new Vector3d(pt.X, pt.Y, pt.Z));
                }
                var dup = src.Geometry.Duplicate();
                dup.Transform(xform);
                var id = Doc.Objects.Add(dup, src.Attributes.Duplicate());
                newIds.Add(id.ToString());
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["source_object_id"] = sourceId,
                    ["curve_id"] = p["curve_id"]!.ToString(),
                    ["object_ids"] = newIds,
                    ["aligned"] = align,
                },
                ["text"] = $"Replicated {newIds.Count} copies along curve",
            };
        }
    }
}

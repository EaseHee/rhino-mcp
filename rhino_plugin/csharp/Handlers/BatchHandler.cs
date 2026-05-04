using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Batch object modification — apply transform and attribute changes
    /// to many objects in a single call, wrapped in one undo record.
    /// </summary>
    public class BatchHandler : HandlerBase
    {
        public JObject Modify(JObject parameters)
        {
            var specs = parameters["objects"] as JArray
                ?? throw new ArgumentException("objects array is required");

            bool applyToAll = parameters["apply_to_all"]?.Value<bool>() ?? false;
            uint undoRecord = Doc.BeginUndoRecord("MCP: batch_modify");

            int successCount = 0;
            int failureCount = 0;
            var errors = new JArray();

            try
            {
                if (applyToAll && specs.Count > 0)
                {
                    var spec = (JObject)specs[0];
                    foreach (var obj in Doc.Objects)
                    {
                        if (ApplySpec(obj, spec, errors))
                            successCount++;
                        else
                            failureCount++;
                    }
                }
                else
                {
                    foreach (var token in specs)
                    {
                        var spec = (JObject)token;
                        var idStr = spec["id"]?.ToString();
                        if (string.IsNullOrEmpty(idStr))
                        {
                            failureCount++;
                            errors.Add(new JObject { ["id"] = "?", ["error"] = "missing id" });
                            continue;
                        }

                        var obj = FindObject(idStr);
                        if (obj == null)
                        {
                            failureCount++;
                            errors.Add(new JObject { ["id"] = idStr, ["error"] = "not found" });
                            continue;
                        }

                        if (ApplySpec(obj, spec, errors))
                            successCount++;
                        else
                            failureCount++;
                    }
                }

                Doc.Views.Redraw();

                return new JObject
                {
                    ["success_count"] = successCount,
                    ["failure_count"] = failureCount,
                    ["total"] = successCount + failureCount,
                    ["errors"] = errors
                };
            }
            finally
            {
                Doc.EndUndoRecord(undoRecord);
            }
        }

        private bool ApplySpec(RhinoObject obj, JObject spec, JArray errors)
        {
            try
            {
                // --- Transforms ---
                var translation = spec["translation"];
                if (translation != null)
                {
                    var vec = ToVector(translation);
                    var xf = Transform.Translation(vec);
                    Doc.Objects.Transform(obj.Id, xf, true);
                }

                var angleDeg = spec["rotation_angle_degrees"]?.Value<double>();
                if (angleDeg.HasValue)
                {
                    var axisToken = spec["rotation_axis"];
                    var axis = axisToken != null ? ToVector(axisToken) : Vector3d.ZAxis;
                    var centerToken = spec["rotation_center"];
                    var center = centerToken != null
                        ? ToPoint(centerToken)
                        : obj.Geometry.GetBoundingBox(true).Center;
                    double radians = angleDeg.Value * Math.PI / 180.0;
                    var xf = Transform.Rotation(radians, axis, center);
                    Doc.Objects.Transform(obj.Id, xf, true);
                }

                var scaleFactor = spec["scale_factor"]?.Value<double>();
                if (scaleFactor.HasValue)
                {
                    var scaleCenterToken = spec["scale_center"];
                    var center = scaleCenterToken != null
                        ? ToPoint(scaleCenterToken)
                        : obj.Geometry.GetBoundingBox(true).Center;
                    var xf = Transform.Scale(center, scaleFactor.Value);
                    Doc.Objects.Transform(obj.Id, xf, true);
                }

                // --- Attributes ---
                bool attrsChanged = false;
                var attrs = obj.Attributes.Duplicate();

                var color = spec["color"] as JArray;
                if (color != null && color.Count >= 3)
                {
                    int r = color[0].Value<int>();
                    int g = color[1].Value<int>();
                    int b = color[2].Value<int>();
                    attrs.ObjectColor = System.Drawing.Color.FromArgb(r, g, b);
                    attrs.ColorSource = ObjectColorSource.ColorFromObject;
                    attrsChanged = true;
                }

                var layer = spec["layer"]?.ToString();
                if (!string.IsNullOrEmpty(layer))
                {
                    int layerIdx = Doc.Layers.FindByFullPath(layer, -1);
                    if (layerIdx < 0)
                    {
                        var newLayer = new Layer { Name = layer };
                        layerIdx = Doc.Layers.Add(newLayer);
                    }
                    attrs.LayerIndex = layerIdx;
                    attrsChanged = true;
                }

                var visible = spec["visible"];
                if (visible != null)
                {
                    attrs.Visible = visible.Value<bool>();
                    attrsChanged = true;
                }

                var name = spec["name"]?.ToString();
                if (name != null)
                {
                    attrs.Name = name;
                    attrsChanged = true;
                }

                if (attrsChanged)
                    Doc.Objects.ModifyAttributes(obj, attrs, true);

                return true;
            }
            catch (Exception ex)
            {
                errors.Add(new JObject
                {
                    ["id"] = obj.Id.ToString(),
                    ["error"] = ex.Message
                });
                return false;
            }
        }
    }
}

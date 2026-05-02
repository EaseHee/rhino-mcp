using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMCPBridge.Handlers
{
    public class QueryHandler : HandlerBase
    {
        private static string SafeLayerName(int layerIndex)
        {
            var layer = Doc.Layers.FindIndex(layerIndex);
            return layer?.Name ?? "";
        }

        public JObject ListObjects(JObject p)
        {
            var layerFilter = p["layer"]?.ToString();
            var kindFilter = p["kind"]?.ToString();
            var offset = p["offset"]?.Value<int>() ?? 0;
            var limit = p["limit"]?.Value<int>() ?? 100;

            var objects = new JArray();
            int totalMatched = 0;
            foreach (var obj in Doc.Objects)
            {
                if (obj.IsDeleted) continue;

                var geom = obj.Geometry;
                if (geom == null) continue;

                var kind = geom.ObjectType.ToString();
                var layerName = SafeLayerName(obj.Attributes.LayerIndex);

                if (!string.IsNullOrEmpty(layerFilter) && layerName != layerFilter)
                    continue;
                if (!string.IsNullOrEmpty(kindFilter) &&
                    !kind.Equals(kindFilter, StringComparison.OrdinalIgnoreCase))
                    continue;

                totalMatched++;
                var position = totalMatched - 1;
                if (position < offset || objects.Count >= limit)
                    continue;

                var bbox = geom.GetBoundingBox(true);
                objects.Add(new JObject
                {
                    ["object_id"] = obj.Id.ToString(),
                    ["kind"] = kind,
                    ["layer"] = layerName,
                    ["name"] = obj.Attributes.Name ?? "",
                    ["bbox"] = BboxJson(bbox)
                });
            }

            var hasMore = offset + objects.Count < totalMatched;
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["count"] = objects.Count,
                    ["offset"] = offset,
                    ["objects"] = objects
                },
                ["pagination"] = new JObject
                {
                    ["total"] = totalMatched,
                    ["offset"] = offset,
                    ["limit"] = limit,
                    ["returned"] = objects.Count,
                    ["has_more"] = hasMore
                },
                ["text"] = $"{objects.Count}/{totalMatched} objects listed (offset={offset}, has_more={hasMore})"
            };
        }

        public JObject ObjectInfo(JObject p)
        {
            var obj = FindObject(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Object not found");
            var geom = obj.Geometry;
            var bbox = geom.GetBoundingBox(true);
            var layerName = SafeLayerName(obj.Attributes.LayerIndex);

            var info = new JObject
            {
                ["object_id"] = obj.Id.ToString(),
                ["kind"] = geom.ObjectType.ToString(),
                ["layer"] = layerName,
                ["name"] = obj.Attributes.Name ?? "",
                ["bbox"] = BboxJson(bbox),
                ["is_valid"] = geom.IsValid
            };

            if (geom is Curve crv)
            {
                info["is_closed"] = crv.IsClosed;
                info["domain"] = new JArray(crv.Domain.Min, crv.Domain.Max);
                info["length"] = crv.GetLength();
            }
            else if (geom is Brep brep)
            {
                info["face_count"] = brep.Faces.Count;
                info["edge_count"] = brep.Edges.Count;
                info["is_solid"] = brep.IsSolid;
                try
                {
                    var vmp = VolumeMassProperties.Compute(brep);
                    if (vmp != null) info["volume"] = vmp.Volume;
                }
                catch { /* non-closed breps may fail */ }
            }
            else if (geom is Mesh mesh)
            {
                info["vertex_count"] = mesh.Vertices.Count;
                info["face_count"] = mesh.Faces.Count;
            }
            else if (geom is Extrusion ext)
            {
                info["is_solid"] = ext.IsSolid;
                info["kind"] = "Extrusion";
            }

            return new JObject
            {
                ["summary"] = info,
                ["text"] = $"{geom.ObjectType}: {obj.Id}"
            };
        }

        public JObject DocumentSummary(JObject p)
        {
            var typeCounts = new JObject();
            foreach (var obj in Doc.Objects)
            {
                if (obj.IsDeleted || obj.Geometry == null) continue;
                var kind = obj.Geometry.ObjectType.ToString();
                typeCounts[kind] = (typeCounts[kind]?.Value<int>() ?? 0) + 1;
            }

            var layers = new JArray();
            foreach (var lay in Doc.Layers)
            {
                if (lay.IsDeleted) continue;
                layers.Add(new JObject
                {
                    ["index"] = lay.Index,
                    ["name"] = lay.Name,
                    ["full_path"] = lay.FullPath,
                    ["color"] = new JObject
                    {
                        ["r"] = lay.Color.R, ["g"] = lay.Color.G, ["b"] = lay.Color.B
                    },
                    ["visible"] = lay.IsVisible,
                    ["locked"] = lay.IsLocked
                });
            }

            var activeCount = 0;
            foreach (var obj in Doc.Objects)
                if (!obj.IsDeleted) activeCount++;

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["total_objects"] = activeCount,
                    ["type_counts"] = typeCounts,
                    ["layer_count"] = layers.Count,
                    ["layers"] = layers,
                    ["file_path"] = Doc.Path ?? "",
                    ["units"] = Doc.ModelUnitSystem.ToString()
                },
                ["text"] = $"Document: {activeCount} objects, {layers.Count} layers"
            };
        }

        public JObject LayerList(JObject p)
        {
            // Pre-count objects per layer
            var layerObjCount = new Dictionary<int, int>();
            foreach (var obj in Doc.Objects)
            {
                if (obj.IsDeleted) continue;
                var idx = obj.Attributes.LayerIndex;
                layerObjCount.TryGetValue(idx, out var c);
                layerObjCount[idx] = c + 1;
            }

            var layers = new JArray();
            foreach (var lay in Doc.Layers)
            {
                if (lay.IsDeleted) continue;
                layerObjCount.TryGetValue(lay.Index, out var objCount);
                layers.Add(new JObject
                {
                    ["index"] = lay.Index,
                    ["name"] = lay.Name,
                    ["full_path"] = lay.FullPath,
                    ["color"] = new JObject
                    {
                        ["r"] = lay.Color.R, ["g"] = lay.Color.G, ["b"] = lay.Color.B
                    },
                    ["visible"] = lay.IsVisible,
                    ["locked"] = lay.IsLocked,
                    ["object_count"] = objCount
                });
            }

            return new JObject
            {
                ["summary"] = new JObject { ["count"] = layers.Count, ["layers"] = layers },
                ["text"] = $"{layers.Count} layers"
            };
        }

        public JObject GetUserText(JObject p)
        {
            var obj = FindObject(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Object not found");
            var key = p["key"]?.ToString();
            if (!string.IsNullOrEmpty(key))
            {
                var val = obj.Attributes.GetUserString(key);
                return new JObject { ["summary"] = new JObject { ["key"] = key, ["value"] = val ?? "" } };
            }
            var keys = obj.Attributes.GetUserStrings();
            var data = new JObject();
            if (keys != null)
            {
                foreach (string? k in keys.AllKeys)
                {
                    if (k != null) data[k] = keys[k];
                }
            }
            return new JObject { ["summary"] = new JObject { ["user_text"] = data, ["count"] = data.Count } };
        }

        public JObject SelectedObjects(JObject p)
        {
            bool includeAttrs = p["include_attributes"]?.Value<bool>() ?? false;
            var selected = Doc.Objects.GetSelectedObjects(false, false);
            var objects = new JArray();

            foreach (var obj in selected)
            {
                if (obj.IsDeleted || obj.Geometry == null) continue;
                var geom = obj.Geometry;
                var bbox = geom.GetBoundingBox(true);
                var item = new JObject
                {
                    ["object_id"] = obj.Id.ToString(),
                    ["kind"] = geom.ObjectType.ToString(),
                    ["layer"] = SafeLayerName(obj.Attributes.LayerIndex),
                    ["name"] = obj.Attributes.Name ?? "",
                    ["bbox"] = BboxJson(bbox)
                };

                if (includeAttrs)
                {
                    var color = obj.Attributes.ObjectColor;
                    item["color"] = new JObject
                    {
                        ["r"] = color.R, ["g"] = color.G, ["b"] = color.B
                    };
                    item["visible"] = obj.Attributes.Visible;
                    item["material_index"] = obj.Attributes.MaterialIndex;
                }

                objects.Add(item);
            }

            return new JObject
            {
                ["count"] = objects.Count,
                ["objects"] = objects
            };
        }

        public JObject SetUserText(JObject p)
        {
            var obj = FindObject(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Object not found");
            var key = p["key"]!.ToString();
            var value = p["value"]!.ToString();
            obj.Attributes.SetUserString(key, value);
            obj.CommitChanges();
            return StatusOk($"User text set: {key}={value}");
        }

        private static JObject BboxJson(BoundingBox bbox)
        {
            return new JObject
            {
                ["min"] = new JObject { ["x"] = bbox.Min.X, ["y"] = bbox.Min.Y, ["z"] = bbox.Min.Z },
                ["max"] = new JObject { ["x"] = bbox.Max.X, ["y"] = bbox.Max.Y, ["z"] = bbox.Max.Z }
            };
        }
    }
}

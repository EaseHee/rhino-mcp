using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Block / instance reuse — define / insert / list / explode / redefine.
    /// Replaces the original ObjectHandler stubs with fully wired handlers.
    /// </summary>
    public class BlockHandler : HandlerBase
    {
        public JObject Define(JObject p)
        {
            var name = p["name"]!.ToString();
            var description = p["description"]?.ToString() ?? "";
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var basePt = ToPoint(p["base_point"]!);
            var replace = p["replace_objects"]?.Value<bool>() ?? true;

            var existing = Doc.InstanceDefinitions.Find(name);
            if (existing != null)
                throw new ArgumentException($"block definition '{name}' already exists");

            var geometry = new List<GeometryBase>();
            var attrs = new List<ObjectAttributes>();
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj == null) continue;
                geometry.Add(obj.Geometry.Duplicate());
                attrs.Add(obj.Attributes.Duplicate());
            }
            var idx = Doc.InstanceDefinitions.Add(name, description, basePt, geometry, attrs);
            if (idx < 0)
                throw new InvalidOperationException("InstanceDefinitions.Add returned -1");
            if (replace)
            {
                foreach (var id in ids) Doc.Objects.Delete(id, true);
                var refId = Doc.Objects.AddInstanceObject(idx, Transform.Translation(new Vector3d(basePt)));
                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject
                    {
                        ["definition_index"] = idx,
                        ["name"] = name,
                        ["object_count"] = geometry.Count,
                        ["instance_id"] = refId.ToString(),
                    },
                    ["text"] = $"Block defined: {name} (replaced {ids.Count} object(s) with 1 instance)",
                };
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["definition_index"] = idx,
                    ["name"] = name,
                    ["object_count"] = geometry.Count,
                },
                ["text"] = $"Block defined: {name} ({geometry.Count} object(s))",
            };
        }

        public JObject Insert(JObject p)
        {
            var name = p["name"]!.ToString();
            var idef = Doc.InstanceDefinitions.Find(name)
                ?? throw new KeyNotFoundException($"block definition not found: {name}");
            var ip = ToPoint(p["insertion_point"]!);
            var scaleArr = p["scale"] as JArray;
            double sx = scaleArr != null ? scaleArr[0].Value<double>() : 1.0;
            double sy = scaleArr != null ? scaleArr[1].Value<double>() : 1.0;
            double sz = scaleArr != null ? scaleArr[2].Value<double>() : 1.0;
            double rotDeg = p["rotation_deg"]?.Value<double>() ?? 0.0;

            var t = Transform.Translation(new Vector3d(ip));
            t *= Transform.Rotation(rotDeg * Math.PI / 180.0, Vector3d.ZAxis, Point3d.Origin);
            t *= Transform.Scale(Plane.WorldXY, sx, sy, sz);

            var attrs = new ObjectAttributes();
            var layerName = p["layer"]?.ToString();
            if (!string.IsNullOrEmpty(layerName))
            {
                var li = Doc.Layers.FindByFullPath(layerName, -1);
                if (li < 0) li = Doc.Layers.Add(new Layer { Name = layerName });
                attrs.LayerIndex = li;
            }
            var instanceName = p["instance_name"]?.ToString();
            if (!string.IsNullOrEmpty(instanceName)) attrs.Name = instanceName;
            var id = Doc.Objects.AddInstanceObject(idef.Index, t, attrs);
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["instance_id"] = id.ToString(),
                    ["definition_name"] = name,
                    ["scale"] = new JArray(sx, sy, sz),
                    ["rotation_deg"] = rotDeg,
                },
                ["text"] = $"Inserted block '{name}' as {id}",
            };
        }

        public JObject List(JObject _)
        {
            var rows = new JArray();
            for (int i = 0; i < Doc.InstanceDefinitions.Count; i++)
            {
                var idef = Doc.InstanceDefinitions[i];
                if (idef == null) continue;
                rows.Add(new JObject
                {
                    ["name"] = idef.Name,
                    ["description"] = idef.Description,
                    ["object_count"] = idef.GetObjects().Length,
                    ["instance_count"] = idef.GetReferences(0).Length,
                });
            }
            return new JObject
            {
                ["summary"] = new JObject { ["definitions"] = rows, ["count"] = rows.Count },
                ["text"] = $"{rows.Count} block definition(s)",
            };
        }

        public JObject Explode(JObject p)
        {
            var idStr = p["instance_id"]!.ToString();
            var keep = p["keep_instance"]?.Value<bool>() ?? false;
            var inst = Doc.Objects.FindId(FindId(idStr)) as InstanceObject
                ?? throw new ArgumentException($"object is not a block instance: {idStr}");
            inst.Explode(true, out var pieces, out _, out _);
            var newIds = new JArray();
            foreach (var piece in pieces)
            {
                var nid = Doc.Objects.Add(piece.Geometry, piece.Attributes);
                newIds.Add(nid.ToString());
            }
            if (!keep) Doc.Objects.Delete(inst.Id, true);
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["instance_id"] = idStr,
                    ["object_ids"] = newIds,
                    ["kept_instance"] = keep,
                },
                ["text"] = $"Exploded instance into {newIds.Count} object(s)",
            };
        }

        public JObject Redefine(JObject p)
        {
            var name = p["name"]!.ToString();
            var idef = Doc.InstanceDefinitions.Find(name)
                ?? throw new KeyNotFoundException($"block definition not found: {name}");
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var basePt = p["base_point"] != null ? ToPoint(p["base_point"]!) : Point3d.Origin;
            var geometry = new List<GeometryBase>();
            var attrs = new List<ObjectAttributes>();
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj == null) continue;
                geometry.Add(obj.Geometry.Duplicate());
                attrs.Add(obj.Attributes.Duplicate());
            }
            var ok = Doc.InstanceDefinitions.ModifyGeometry(idef.Index, geometry, attrs);
            if (!ok) throw new InvalidOperationException($"redefine failed for '{name}'");
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["name"] = name,
                    ["definition_index"] = idef.Index,
                    ["object_count"] = geometry.Count,
                },
                ["text"] = $"Redefined block '{name}' with {geometry.Count} object(s)",
            };
        }
    }
}

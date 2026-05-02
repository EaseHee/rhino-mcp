using Newtonsoft.Json.Linq;
using Rhino.DocObjects;

namespace RhinoMCPBridge.Handlers
{
    public class LayerHandler : HandlerBase
    {
        public JObject Create(JObject p)
        {
            var name = p["name"]!.ToString();
            var existing = Doc.Layers.FindByFullPath(name, -1);
            if (existing >= 0)
                return new JObject
                {
                    ["summary"] = new JObject { ["layer_index"] = existing, ["name"] = name, ["created"] = false },
                    ["text"] = $"Layer already exists: {name}"
                };

            var layer = new Layer { Name = name };

            if (p["color"] != null)
            {
                var c = p["color"]!;
                layer.Color = System.Drawing.Color.FromArgb(
                    c["r"]!.Value<int>(), c["g"]!.Value<int>(), c["b"]!.Value<int>());
            }
            if (p["parent"] != null)
            {
                var parentIdx = Doc.Layers.FindByFullPath(p["parent"]!.ToString(), -1);
                if (parentIdx >= 0)
                    layer.ParentLayerId = Doc.Layers[parentIdx].Id;
            }

            var idx = Doc.Layers.Add(layer);
            return new JObject
            {
                ["summary"] = new JObject { ["layer_index"] = idx, ["name"] = name, ["created"] = true },
                ["text"] = $"Layer created: {name}"
            };
        }

        public JObject Delete(JObject p)
        {
            var name = p["name"]!.ToString();
            var idx = Doc.Layers.FindByFullPath(name, -1);
            if (idx < 0) throw new KeyNotFoundException($"Layer not found: {name}");
            Doc.Layers.Delete(idx, true);
            return StatusOk($"Layer deleted: {name}");
        }

        public JObject SetColor(JObject p)
        {
            var name = p["name"]!.ToString();
            var idx = Doc.Layers.FindByFullPath(name, -1);
            if (idx < 0) throw new KeyNotFoundException($"Layer not found: {name}");
            var layer = Doc.Layers[idx];
            var c = p["color"]!;
            layer.Color = System.Drawing.Color.FromArgb(
                c["r"]!.Value<int>(), c["g"]!.Value<int>(), c["b"]!.Value<int>());
            Doc.Layers.Modify(layer, idx, true);
            return StatusOk($"Layer color set: {name}");
        }
    }

    public class MaterialHandler : HandlerBase
    {
        public JObject Create(JObject p)
        {
            var name = p["name"]!.ToString();
            var idx = Doc.Materials.Find(name, true);
            if (idx >= 0)
                return new JObject
                {
                    ["summary"] = new JObject { ["material_index"] = idx, ["name"] = name },
                    ["text"] = $"Material exists: {name}"
                };

            var mat = new Rhino.DocObjects.Material { Name = name };
            if (p["color"] != null)
            {
                var c = p["color"]!;
                mat.DiffuseColor = System.Drawing.Color.FromArgb(
                    c["r"]!.Value<int>(), c["g"]!.Value<int>(), c["b"]!.Value<int>());
            }
            idx = Doc.Materials.Add(mat);
            return new JObject
            {
                ["summary"] = new JObject { ["material_index"] = idx, ["name"] = name },
                ["text"] = $"Material created: {name}"
            };
        }

        public JObject Assign(JObject p)
        {
            var name = p["material_name"]!.ToString();
            var matIdx = Doc.Materials.Find(name, true);
            if (matIdx < 0) throw new KeyNotFoundException($"Material not found: {name}");
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj == null) continue;
                var attrs = obj.Attributes;
                attrs.MaterialIndex = matIdx;
                attrs.MaterialSource = ObjectMaterialSource.MaterialFromObject;
                Doc.Objects.ModifyAttributes(obj, attrs, true);
            }
            return StatusOk($"Material '{name}' assigned to {ids.Count} objects");
        }
    }
}

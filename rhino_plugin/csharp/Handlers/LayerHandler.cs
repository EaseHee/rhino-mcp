using Newtonsoft.Json.Linq;
using Rhino.DocObjects;

namespace RhinoMcp.Handlers
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

            // ``color`` is optional. Guard against JSON ``null`` (which arrives
            // as JValue.Null and would explode on the c["r"] indexer below) by
            // requiring a real JObject.
            if (p["color"] is JObject c)
            {
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
            if (p["color"] is not JObject c)
                throw new System.ArgumentException("'color' must be an object {r, g, b}.");
            layer.Color = System.Drawing.Color.FromArgb(
                c["r"]!.Value<int>(), c["g"]!.Value<int>(), c["b"]!.Value<int>());
            Doc.Layers.Modify(layer, idx, true);
            return StatusOk($"Layer color set: {name}");
        }

        public JObject SetMaterial(JObject p)
        {
            var name = p["name"]!.ToString();
            var idx = Doc.Layers.FindByFullPath(name, -1);
            if (idx < 0) throw new KeyNotFoundException($"Layer not found: {name}");
            var matName = p["material_name"]?.ToString();
            var matIdx = p["material_index"]?.Value<int>() ?? -1;
            if (matIdx < 0 && !string.IsNullOrEmpty(matName))
                matIdx = Doc.Materials.Find(matName, true);
            if (matIdx < 0)
                throw new KeyNotFoundException($"Material not found: {matName ?? "<unset>"}");
            var layer = Doc.Layers[idx];
            layer.RenderMaterialIndex = matIdx;
            Doc.Layers.Modify(layer, idx, true);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["layer"] = name,
                    ["layer_index"] = idx,
                    ["material_index"] = matIdx,
                    ["material_name"] = matName ?? Doc.Materials[matIdx]?.Name,
                },
                ["text"] = $"Material '{matName ?? matIdx.ToString()}' bound to layer {name}",
            };
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
            if (p["color"] is JObject c)
            {
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

        public JObject PresetCreate(JObject p)
        {
            var name = p["material_name"]!.ToString();
            var spec = p["spec"] as JObject ?? throw new ArgumentException("missing 'spec' payload");
            var diffuseArr = spec["diffuse"] as JArray;
            var color = diffuseArr != null
                ? System.Drawing.Color.FromArgb(
                    diffuseArr[0].Value<int>(), diffuseArr[1].Value<int>(), diffuseArr[2].Value<int>())
                : System.Drawing.Color.Gray;
            double transparency = spec["transparency"]?.Value<double>() ?? 0.0;
            double glossiness = spec["glossiness"]?.Value<double>() ?? 0.0;
            double reflectivity = spec["reflectivity"]?.Value<double>() ?? 0.04;
            double ior = spec["ior"]?.Value<double>() ?? 1.5;

            var mat = new Rhino.DocObjects.Material
            {
                Name = name,
                DiffuseColor = color,
                Transparency = transparency,
                Shine = glossiness * Rhino.DocObjects.Material.MaxShine,
                Reflectivity = reflectivity,
                IndexOfRefraction = ior,
            };
            int idx = Doc.Materials.Add(mat);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["name"] = name,
                    ["preset"] = p["preset_name"]?.ToString(),
                    ["category"] = spec["category"]?.ToString(),
                    ["index"] = idx,
                    ["transparency"] = transparency,
                    ["glossiness"] = glossiness,
                    ["reflectivity"] = reflectivity,
                    ["ior"] = ior,
                },
                ["text"] = $"Created material '{name}' from preset",
            };
        }

        public JObject EnvironmentSet(JObject p)
        {
            var hdri = p["hdri_path"]!.ToString();
            double rotation = p["rotation_deg"]?.Value<double>() ?? 0.0;
            double strength = p["background_strength"]?.Value<double>() ?? 1.0;
            bool forLighting = p["use_for_lighting"]?.Value<bool>() ?? true;
            bool forBackground = p["use_for_background"]?.Value<bool>() ?? true;

            // Persist as document strings for downstream render engines that
            // read the active environment from Rhino's RenderSettings.
            Doc.Strings.SetString("rhino_mcp::env_hdri", hdri);
            Doc.Strings.SetString("rhino_mcp::env_rotation_deg", rotation.ToString("R"));
            Doc.Strings.SetString("rhino_mcp::env_strength", strength.ToString("R"));
            Doc.Strings.SetString("rhino_mcp::env_for_lighting", forLighting ? "1" : "0");
            Doc.Strings.SetString("rhino_mcp::env_for_background", forBackground ? "1" : "0");
            SafeRunScript($"_-Environment _SetActive _File \"{hdri}\" _Enter");
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["hdri_path"] = hdri,
                    ["rotation_deg"] = rotation,
                    ["background_strength"] = strength,
                    ["use_for_lighting"] = forLighting,
                    ["use_for_background"] = forBackground,
                },
                ["text"] = $"HDRI environment set: {hdri}",
            };
        }
    }
}

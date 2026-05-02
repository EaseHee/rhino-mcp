using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMCPBridge.Handlers
{
    /// <summary>
    /// Loads bundled Grasshopper templates and binds their declared
    /// parameters by name. The Python side ships the manifest contract;
    /// this handler resolves named parameters to the actual GH special
    /// components (sliders, panels, toggles) on the loaded canvas.
    /// </summary>
    public class GhTemplatesHandler : HandlerBase
    {
        // Map from template_id (we hand back to Python) → loaded GH document.
        private static readonly Dictionary<string, Grasshopper.Kernel.GH_Document> Loaded = new();

        public JObject Load(JObject p)
        {
            var name = p["name"]!.ToString();
            var path = p["path"]!.ToString();
            if (!System.IO.File.Exists(path))
                throw new System.IO.FileNotFoundException($"GH template not found: {path}");

            var io = new Grasshopper.Kernel.GH_DocumentIO();
            if (!io.Open(path))
                throw new InvalidOperationException($"Failed to open GH file: {path}");
            var doc = io.Document;
            Grasshopper.Instances.DocumentServer.AddDocument(doc);

            // Discover named special components — the manifest's parameter names
            // must match the GH component nicknames so the LLM can bind by name.
            var paramMap = new JObject();
            foreach (var obj in doc.Objects)
            {
                if (obj is Grasshopper.Kernel.IGH_DocumentObject dobj)
                {
                    var nick = dobj.NickName;
                    if (string.IsNullOrEmpty(nick)) continue;
                    var kind = obj switch
                    {
                        Grasshopper.Kernel.Special.GH_NumberSlider => "slider",
                        Grasshopper.Kernel.Special.GH_BooleanToggle => "toggle",
                        Grasshopper.Kernel.Special.GH_Panel => "panel",
                        _ => null,
                    };
                    if (kind != null)
                    {
                        paramMap[nick] = new JObject
                        {
                            ["component_id"] = dobj.InstanceGuid.ToString(),
                            ["kind"] = kind,
                        };
                    }
                }
            }

            var templateId = $"{name}:{Guid.NewGuid():N}";
            Loaded[templateId] = doc;
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["template_id"] = templateId,
                    ["name"] = name,
                    ["parameters"] = paramMap,
                },
                ["text"] = $"Loaded template '{name}' with {paramMap.Count} bindable parameter(s)",
            };
        }

        public JObject BindParameter(JObject p)
        {
            var templateId = p["template_id"]!.ToString();
            if (!Loaded.TryGetValue(templateId, out var doc))
                throw new KeyNotFoundException($"template_id not loaded: {templateId}");
            var paramName = p["parameter"]!.ToString();
            var value = p["value"]!;

            foreach (var obj in doc.Objects)
            {
                if (obj is Grasshopper.Kernel.IGH_DocumentObject dobj
                    && string.Equals(dobj.NickName, paramName, StringComparison.OrdinalIgnoreCase))
                {
                    switch (obj)
                    {
                        case Grasshopper.Kernel.Special.GH_NumberSlider slider:
                            slider.SetSliderValue(value.Value<decimal>());
                            slider.ExpireSolution(true);
                            return new JObject
                            {
                                ["summary"] = new JObject
                                {
                                    ["template_id"] = templateId,
                                    ["parameter"] = paramName,
                                    ["kind"] = "slider",
                                    ["value"] = value.Value<double>(),
                                },
                                ["text"] = $"Slider '{paramName}' = {value}",
                            };
                        case Grasshopper.Kernel.Special.GH_BooleanToggle toggle:
                            toggle.Value = value.Value<bool>();
                            toggle.ExpireSolution(true);
                            return new JObject
                            {
                                ["summary"] = new JObject
                                {
                                    ["template_id"] = templateId,
                                    ["parameter"] = paramName,
                                    ["kind"] = "toggle",
                                    ["value"] = value.Value<bool>(),
                                },
                                ["text"] = $"Toggle '{paramName}' = {value}",
                            };
                        case Grasshopper.Kernel.Special.GH_Panel panel:
                            panel.SetUserText(value.ToString());
                            panel.ExpireSolution(true);
                            return new JObject
                            {
                                ["summary"] = new JObject
                                {
                                    ["template_id"] = templateId,
                                    ["parameter"] = paramName,
                                    ["kind"] = "panel",
                                    ["value"] = value.ToString(),
                                },
                                ["text"] = $"Panel '{paramName}' = {value}",
                            };
                    }
                }
            }
            throw new KeyNotFoundException($"parameter '{paramName}' not found on template '{templateId}'");
        }

        public JObject Run(JObject p)
        {
            var templateId = p["template_id"]!.ToString();
            if (!Loaded.TryGetValue(templateId, out var doc))
                throw new KeyNotFoundException($"template_id not loaded: {templateId}");
            var bake = p["bake"]?.Value<bool>() ?? true;
            var layer = p["layer"]?.ToString() ?? "Templates";

            doc.NewSolution(true);

            int baked = 0;
            if (bake)
            {
                // Baking layer prep
                int layerIndex = Doc.Layers.FindByFullPath(layer, -1);
                if (layerIndex < 0)
                {
                    var l = new Rhino.DocObjects.Layer { Name = layer };
                    layerIndex = Doc.Layers.Add(l);
                }
                var attrs = new Rhino.DocObjects.ObjectAttributes { LayerIndex = layerIndex };
                foreach (var obj in doc.Objects)
                {
                    if (obj is Grasshopper.Kernel.IGH_BakeAwareObject baker && baker.IsBakeCapable)
                    {
                        var ids = new List<Guid>();
                        baker.BakeGeometry(Doc, attrs, ids);
                        baked += ids.Count;
                    }
                }
                Doc.Views.Redraw();
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["template_id"] = templateId,
                    ["baked_count"] = baked,
                    ["layer"] = layer,
                },
                ["text"] = $"Solution complete; baked {baked} object(s) onto '{layer}'",
            };
        }
    }
}

using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Grasshopper canvas, component, parameter, and data tree operations.
    /// Grasshopper.Instances is only available when the GH editor has been
    /// opened at least once in the session.
    /// </summary>
    public class GrasshopperHandler : HandlerBase
    {
        private static Grasshopper.Kernel.GH_Document GetDoc()
        {
            var server = Grasshopper.Instances.DocumentServer;
            if (server == null || server.DocumentCount == 0)
                throw new InvalidOperationException("No active Grasshopper document. Open the GH editor first.");
            return server[0];
        }

        // ── Canvas ───────────────────────────────────────────────────────────
        public JObject CanvasOpen(JObject p)
        {
            var path = p["path"]!.ToString();
            var io = new Grasshopper.Kernel.GH_DocumentIO();
            if (!io.Open(path))
                throw new InvalidOperationException($"Failed to open GH file: {path}");
            Grasshopper.Instances.DocumentServer.AddDocument(io.Document);
            return StatusOk($"Opened GH file: {path}");
        }

        public JObject CanvasSave(JObject p)
        {
            var doc = GetDoc();
            var path = p["path"]?.ToString() ?? doc.FilePath;
            var archive = new GH_IO.Serialization.GH_Archive();
            archive.CreateTopLevelNode("Definition");
            doc.Write(archive.GetRootNode);
            archive.Path = path;
            archive.WriteToFile(path, true, false);
            doc.FilePath = path;
            return StatusOk($"Saved: {path}");
        }

        public JObject CanvasNew(JObject p)
        {
            Grasshopper.Instances.DocumentServer.AddDocument(new Grasshopper.Kernel.GH_Document());
            return StatusOk("New GH document created");
        }

        public JObject CanvasRun(JObject p)
        {
            GetDoc().NewSolution(true);
            return StatusOk("Solution recomputed");
        }

        public JObject CanvasReset(JObject p)
        {
            var doc = GetDoc();
            doc.RemoveObjects(doc.Objects.ToList(), false);
            return StatusOk("Canvas cleared");
        }

        public JObject CanvasPreviewToggle(JObject p)
        {
            var enabled = p["enabled"]?.Value<bool>() ?? true;
            GetDoc().PreviewMode = enabled
                ? Grasshopper.Kernel.GH_PreviewMode.Shaded
                : Grasshopper.Kernel.GH_PreviewMode.Disabled;
            return StatusOk($"Preview: {(enabled ? "on" : "off")}");
        }

        public JObject CanvasBake(JObject p)
        {
            var doc = GetDoc();
            var layer = p["layer"]?.ToString();
            var baked = new JArray();

            var componentIds = p["component_ids"]!.Select(t => new Guid(t.ToString())).ToList();
            foreach (var gid in componentIds)
            {
                var obj = doc.FindObject(gid, true);
                if (obj == null) continue;

                var attrs = new Rhino.DocObjects.ObjectAttributes();
                if (!string.IsNullOrEmpty(layer))
                {
                    var layerIdx = Doc.Layers.FindByFullPath(layer, -1);
                    if (layerIdx < 0)
                    {
                        var l = new Rhino.DocObjects.Layer { Name = layer };
                        layerIdx = Doc.Layers.Add(l);
                    }
                    attrs.LayerIndex = layerIdx;
                }

                // Bake volatile data
                if (obj is Grasshopper.Kernel.IGH_Component comp)
                {
                    foreach (var output in comp.Params.Output)
                    {
                        foreach (var goo in output.VolatileData.AllData(true))
                        {
                            var geom = Grasshopper.Kernel.GH_Convert.ToGeometryBase(goo);
                            if (geom != null)
                            {
                                var id = Doc.Objects.Add(geom, attrs);
                                baked.Add(id.ToString());
                            }
                        }
                    }
                }
            }

            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_ids"] = baked },
                ["text"] = $"Baked {baked.Count} objects"
            };
        }

        // ── Components ───────────────────────────────────────────────────────
        public JObject ComponentAdd(JObject p)
        {
            var name = p["name"]!.ToString();
            var x = p["x"]?.Value<float>() ?? 0;
            var y = p["y"]?.Value<float>() ?? 0;

            var proxy = Grasshopper.Instances.ComponentServer.FindObjectByName(name, true, true);
            if (proxy == null)
                throw new KeyNotFoundException($"GH component not found: {name}");

            var obj = Grasshopper.Instances.ComponentServer.EmitObject(proxy.Guid)
                ?? throw new InvalidOperationException($"Failed to create: {name}");
            obj.Attributes.Pivot = new System.Drawing.PointF(x, y);

            GetDoc().AddObject(obj, false);
            GetDoc().NewSolution(false);

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["component_id"] = obj.InstanceGuid.ToString(),
                    ["name"] = name
                },
                ["text"] = $"Added component: {name}"
            };
        }

        public JObject ComponentDelete(JObject p)
        {
            var doc = GetDoc();
            var id = new Guid(p["component_id"]!.ToString());
            var obj = doc.FindObject(id, true);
            if (obj == null) throw new KeyNotFoundException("Component not found");
            doc.RemoveObject(obj, false);
            return StatusOk("Component deleted");
        }

        public JObject ComponentConnect(JObject p)
        {
            var doc = GetDoc();
            var srcId = new Guid(p["source_id"]!.ToString());
            var srcIdx = p["source_output"]?.Value<int>() ?? 0;
            var tgtId = new Guid(p["target_id"]!.ToString());
            var tgtIdx = p["target_input"]?.Value<int>() ?? 0;

            var src = doc.FindObject(srcId, true) as Grasshopper.Kernel.IGH_Component
                ?? throw new KeyNotFoundException("Source component not found");
            var tgt = doc.FindObject(tgtId, true) as Grasshopper.Kernel.IGH_Component
                ?? throw new KeyNotFoundException("Target component not found");

            var output = src.Params.Output[srcIdx];
            var input = tgt.Params.Input[tgtIdx];
            input.AddSource(output);
            doc.NewSolution(false);

            return StatusOk("Connected");
        }

        public JObject ComponentList(JObject p)
        {
            var doc = GetDoc();
            var components = new JArray();
            foreach (var obj in doc.Objects)
            {
                components.Add(new JObject
                {
                    ["id"] = obj.InstanceGuid.ToString(),
                    ["name"] = obj.Name,
                    ["type"] = obj.GetType().Name,
                    ["x"] = obj.Attributes.Pivot.X,
                    ["y"] = obj.Attributes.Pivot.Y
                });
            }
            return new JObject { ["summary"] = new JObject { ["components"] = components } };
        }

        public JObject ClusterCreate(JObject p)
        {
            RhinoApp.RunScript("_GrasshopperCluster", false);
            return StatusOk("Cluster creation invoked");
        }

        public JObject ClusterExpand(JObject p)
        {
            RhinoApp.RunScript("_GrasshopperClusterExpand", false);
            return StatusOk("Cluster expand invoked");
        }

        // ── Parameters ───────────────────────────────────────────────────────
        public JObject ParameterGet(JObject p)
        {
            var doc = GetDoc();
            var id = new Guid(p["component_id"]!.ToString());
            var obj = doc.FindObject(id, true)
                ?? throw new KeyNotFoundException("Component not found");

            var data = new JArray();
            if (obj is Grasshopper.Kernel.IGH_Param param)
            {
                foreach (var goo in param.VolatileData.AllData(true))
                    data.Add(goo.ToString());
            }
            return new JObject
            {
                ["summary"] = new JObject { ["values"] = data, ["count"] = data.Count }
            };
        }

        public JObject ParameterSet(JObject p)
        {
            // Generic parameter set — delegates to specific type handlers
            var type = p["type"]?.ToString() ?? "string";
            return type switch
            {
                "slider" => ParameterSetSlider(p),
                "toggle" => ParameterSetToggle(p),
                "panel" => ParameterSetPanel(p),
                _ => ParameterSetPanel(p)
            };
        }

        public JObject ParameterSetSlider(JObject p)
        {
            var doc = GetDoc();
            var id = new Guid(p["component_id"]!.ToString());
            var obj = doc.FindObject(id, true) as Grasshopper.Kernel.Special.GH_NumberSlider
                ?? throw new KeyNotFoundException("Slider not found");
            var value = p["value"]!.Value<decimal>();
            obj.SetSliderValue(value);
            obj.ExpireSolution(true);
            return new JObject
            {
                ["summary"] = new JObject { ["component_id"] = id.ToString(), ["value"] = value },
                ["text"] = $"Slider set to {value}"
            };
        }

        public JObject ParameterSetToggle(JObject p)
        {
            var doc = GetDoc();
            var id = new Guid(p["component_id"]!.ToString());
            var obj = doc.FindObject(id, true) as Grasshopper.Kernel.Special.GH_BooleanToggle
                ?? throw new KeyNotFoundException("Toggle not found");
            var value = p["value"]!.Value<bool>();
            obj.Value = value;
            obj.ExpireSolution(true);
            return StatusOk($"Toggle set to {value}");
        }

        public JObject ParameterSetPanel(JObject p)
        {
            var doc = GetDoc();
            var id = new Guid(p["component_id"]!.ToString());
            var obj = doc.FindObject(id, true) as Grasshopper.Kernel.Special.GH_Panel
                ?? throw new KeyNotFoundException("Panel not found");
            var value = p["value"]!.ToString();
            obj.SetUserText(value);
            obj.ExpireSolution(true);
            return StatusOk($"Panel set to: {value}");
        }

        // ── Data Tree ────────────────────────────────────────────────────────
        public JObject DataTreeGet(JObject p)
        {
            var doc = GetDoc();
            var id = new Guid(p["component_id"]!.ToString());
            var obj = doc.FindObject(id, true) as Grasshopper.Kernel.IGH_Param
                ?? throw new KeyNotFoundException("Parameter not found");

            var tree = new JObject();
            var data = obj.VolatileData;
            for (int i = 0; i < data.PathCount; i++)
            {
                var path = data.get_Path(i);
                var branch = data.get_Branch(path);
                var values = new JArray();
                foreach (var goo in branch)
                    values.Add(goo?.ToString() ?? "null");
                tree[path.ToString()] = values;
            }
            return new JObject { ["summary"] = new JObject { ["tree"] = tree } };
        }

        public JObject DataTreeSet(JObject p)
        {
            // Setting data tree values is complex — delegate to parameter set
            return ParameterSet(p);
        }
    }
}

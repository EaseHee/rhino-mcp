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

        // ── Plugin catalog ────────────────────────────────────────────────────
        public JObject PluginList(JObject p)
        {
            var server = Grasshopper.Instances.ComponentServer;
            var libraries = new JArray();
            if (server != null)
            {
                foreach (var lib in server.Libraries)
                {
                    // GH_AssemblyInfo exposes a small fixed set of fields; the
                    // author surface is typed differently between Rhino 7/8 so
                    // we read it via reflection and degrade gracefully.
                    string author = "";
                    try
                    {
                        var prop = lib.GetType().GetProperty("AuthorName")
                            ?? lib.GetType().GetProperty("Author");
                        author = prop?.GetValue(lib)?.ToString() ?? "";
                    }
                    catch
                    {
                        // best-effort
                    }
                    libraries.Add(new JObject
                    {
                        ["id"] = lib.Id.ToString(),
                        ["name"] = lib.Name,
                        ["author"] = author,
                        ["version"] = lib.Version,
                        ["description"] = lib.Description,
                        ["assembly_full_name"] = lib.Assembly?.FullName,
                        ["assembly_path"] = lib.Location,
                    });
                }
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["library_count"] = libraries.Count,
                    ["libraries"] = libraries,
                },
                ["text"] = $"{libraries.Count} Grasshopper plugin libraries loaded.",
            };
        }

        public JObject ComponentsSearch(JObject p)
        {
            var server = Grasshopper.Instances.ComponentServer;
            if (server == null)
                throw new InvalidOperationException("Grasshopper.ComponentServer not available.");

            var query = (p["query"]?.ToString() ?? "").Trim();
            var pluginFilter = (p["plugin"]?.ToString() ?? "").Trim();
            var category = (p["category"]?.ToString() ?? "").Trim();
            var limit = p["limit"]?.Value<int>() ?? 50;
            if (limit <= 0) limit = 50;
            if (limit > 500) limit = 500;

            var rows = new JArray();
            int matched = 0;
            foreach (var proxy in server.ObjectProxies)
            {
                if (proxy == null || proxy.Obsolete) continue;
                var name = proxy.Desc.Name ?? "";
                var nick = proxy.Desc.NickName ?? "";
                var cat = proxy.Desc.Category ?? "";
                var sub = proxy.Desc.SubCategory ?? "";
                var plugin = proxy.Location?.Split('/', '\\') is { Length: > 0 } parts
                    ? parts[parts.Length - 1]
                    : "";

                if (!string.IsNullOrEmpty(query)
                    && name.IndexOf(query, StringComparison.OrdinalIgnoreCase) < 0
                    && nick.IndexOf(query, StringComparison.OrdinalIgnoreCase) < 0
                    && sub.IndexOf(query, StringComparison.OrdinalIgnoreCase) < 0)
                    continue;
                if (!string.IsNullOrEmpty(category)
                    && cat.IndexOf(category, StringComparison.OrdinalIgnoreCase) < 0
                    && sub.IndexOf(category, StringComparison.OrdinalIgnoreCase) < 0)
                    continue;
                if (!string.IsNullOrEmpty(pluginFilter)
                    && plugin.IndexOf(pluginFilter, StringComparison.OrdinalIgnoreCase) < 0)
                    continue;

                matched++;
                if (rows.Count >= limit) continue;
                rows.Add(new JObject
                {
                    ["guid"] = proxy.Guid.ToString(),
                    ["name"] = name,
                    ["nickname"] = nick,
                    ["category"] = cat,
                    ["subcategory"] = sub,
                    ["description"] = proxy.Desc.Description ?? "",
                    ["plugin"] = plugin,
                });
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["query"] = query,
                    ["plugin_filter"] = pluginFilter,
                    ["category_filter"] = category,
                    ["matched"] = matched,
                    ["returned"] = rows.Count,
                    ["limit"] = limit,
                },
                ["rows"] = rows,
                ["text"] = $"Matched {matched} components, returning {rows.Count}.",
            };
        }

        public JObject ClusterCreate(JObject p)
        {
            SafeRunScript("_GrasshopperCluster");
            return StatusOk("Cluster creation invoked");
        }

        public JObject ClusterExpand(JObject p)
        {
            SafeRunScript("_GrasshopperClusterExpand");
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

        public JObject DataTreeGetBatch(JObject p)
        {
            var queries = p["queries"] as JArray
                ?? throw new System.ArgumentException("'queries' must be a JSON array.");
            var rows = new JArray();
            foreach (var q in queries)
            {
                var qo = q as JObject
                    ?? throw new System.ArgumentException("Each query must be an object.");
                var entry = new JObject { ["component_id"] = qo["component_id"] };
                try
                {
                    var single = DataTreeGet(qo);
                    entry["status"] = "ok";
                    entry["tree"] = single["summary"]?["tree"];
                }
                catch (System.Exception ex)
                {
                    entry["status"] = "error";
                    entry["error"] = ex.Message;
                }
                rows.Add(entry);
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["query_count"] = queries.Count,
                    ["returned"] = rows.Count,
                },
                ["rows"] = rows,
            };
        }

        public JObject DataTreeSetBatch(JObject p)
        {
            var assignments = p["assignments"] as JArray
                ?? throw new System.ArgumentException("'assignments' must be a JSON array.");
            var deferSolve = p["defer_solve"]?.Value<bool>() ?? true;
            var rows = new JArray();
            var ok = 0;
            var failed = 0;
            var doc = GetDoc();
            // Suspend the solver across the batch so the document recomputes
            // exactly once at the end instead of after every assignment.
            var prevEnabled = doc.Enabled;
            if (deferSolve)
            {
                try { doc.Enabled = false; } catch { /* best-effort */ }
            }
            foreach (var a in assignments)
            {
                var ao = a as JObject
                    ?? throw new System.ArgumentException("Each assignment must be an object.");
                var entry = new JObject
                {
                    ["component_id"] = ao["component_id"],
                };
                try
                {
                    ParameterSet(ao);
                    entry["status"] = "ok";
                    ok++;
                }
                catch (System.Exception ex)
                {
                    entry["status"] = "error";
                    entry["error"] = ex.Message;
                    failed++;
                }
                rows.Add(entry);
            }
            if (deferSolve)
            {
                try { doc.Enabled = prevEnabled; } catch { /* best-effort */ }
                try { doc.NewSolution(false); } catch { /* best-effort */ }
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["assignment_count"] = assignments.Count,
                    ["ok"] = ok,
                    ["failed"] = failed,
                    ["defer_solve"] = deferSolve,
                },
                ["rows"] = rows,
            };
        }
    }
}

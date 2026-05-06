using System.IO;
using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;

namespace RhinoMcp.Handlers
{
    public class IOHandler : HandlerBase
    {
        private static string RequirePath(JObject p, string field = "path")
        {
            var raw = p[field]?.ToString();
            if (string.IsNullOrWhiteSpace(raw))
                throw new System.ArgumentException($"{field} is required and must be a non-empty string.");
            // Reject quote characters that would break the RunScript framing.
            if (raw.Contains('"'))
                throw new System.ArgumentException($"{field} must not contain double-quote characters.");
            return raw;
        }

        public JObject Open(JObject p)
        {
            var path = RequirePath(p);
            SafeRunScript($"_-Open \"{path}\"", nameof(Open));
            return StatusOk($"Opened: {path}");
        }

        public JObject Save(JObject p)
        {
            var path = p["path"]?.ToString();
            if (!string.IsNullOrEmpty(path))
            {
                if (path.Contains('"'))
                    throw new System.ArgumentException("path must not contain double-quote characters.");
                SafeRunScript($"_-SaveAs \"{path}\"", nameof(Save));
            }
            else
            {
                SafeRunScript("_-Save", nameof(Save));
            }
            return StatusOk("Document saved");
        }

        public JObject Import(JObject p)
        {
            var path = RequirePath(p);
            SafeRunScript($"_-Import \"{path}\" _Enter", nameof(Import));
            return StatusOk($"Imported: {path}");
        }

        public JObject ExportStep(JObject p) => Export(p, "_-Export", "STEP", nameof(ExportStep));
        public JObject ExportIges(JObject p) => Export(p, "_-Export", "IGES", nameof(ExportIges));
        public JObject ExportObj(JObject p) => Export(p, "_-Export", "OBJ", nameof(ExportObj));
        public JObject ExportStl(JObject p) => Export(p, "_-Export", "STL", nameof(ExportStl));
        public JObject ExportDxf(JObject p) => Export(p, "_-Export", "DXF", nameof(ExportDxf));

        public JObject Screenshot(JObject p)
        {
            // Accept both ``path`` (Python tool side) and ``output_path``
            // (legacy contract) so the handler stays robust to either caller.
            var path = p["path"]?.ToString() ?? p["output_path"]?.ToString();
            if (string.IsNullOrWhiteSpace(path))
                throw new System.ArgumentException("Screenshot requires 'path' (or 'output_path').");
            if (path.Contains('"'))
                throw new System.ArgumentException("path must not contain double-quote characters.");

            var width = p["width"]?.Value<int>() ?? 1920;
            var height = p["height"]?.Value<int>() ?? 1080;
            if (width <= 0 || height <= 0)
                throw new System.ArgumentException(
                    $"width/height must be positive integers (got width={width}, height={height}).");
            // Cap absurd sizes that would only ever come from a bug. ViewCapture
            // happily allocates gigabytes otherwise.
            if (width > 16384 || height > 16384)
                throw new System.ArgumentException(
                    $"width/height must be <= 16384 (got width={width}, height={height}).");

            var asBase64 = p["as_base64"]?.Value<bool>() ?? false;

            SafeRunScript(
                $"_-ViewCaptureToFile \"{path}\" _Width={width} _Height={height} _Enter",
                nameof(Screenshot));

            var summary = new JObject
            {
                ["path"] = path,
                ["width"] = width,
                ["height"] = height,
            };
            var response = new JObject
            {
                ["status"] = "ok",
                ["summary"] = summary,
                ["text"] = $"Captured viewport to {path} ({width}x{height})",
            };

            if (asBase64 && File.Exists(path))
            {
                try
                {
                    var bytes = File.ReadAllBytes(path);
                    response["image_base64"] = System.Convert.ToBase64String(bytes);
                    response["mime"] = "image/png";
                }
                catch (System.Exception ex)
                {
                    // Don't fail the whole call if base64 encoding hits an IO snag;
                    // surface the file path so the LLM can fall back to a manual read.
                    response["base64_error"] = ex.Message;
                }
            }
            return response;
        }

        private static JObject Export(JObject p, string cmd, string format, string opName)
        {
            var path = RequirePath(p);
            SafeRunScript($"{cmd} \"{path}\" _Enter", opName);
            return StatusOk($"Exported {format}: {path}");
        }

        public JObject ViewportPreview(JObject p)
        {
            var path = p["path"]?.ToString();
            if (string.IsNullOrWhiteSpace(path))
                throw new System.ArgumentException("path is required.");
            if (path.Contains('"'))
                throw new System.ArgumentException("path must not contain double-quote characters.");
            var width = p["width"]?.Value<int>() ?? 1920;
            var height = p["height"]?.Value<int>() ?? 1080;
            if (width <= 0 || height <= 0 || width > 16384 || height > 16384)
                throw new System.ArgumentException("width/height must be 1..16384.");
            var ghostOthers = p["ghost_others"]?.Value<bool>() ?? true;
            var zoomToSelection = p["zoom_to_selection"]?.Value<bool>() ?? true;

            var selectionIds = (p["selection_ids"] as JArray)?
                .Select(t => Guid.TryParse(t?.ToString(), out var g) ? g : Guid.Empty)
                .Where(g => g != Guid.Empty)
                .ToHashSet() ?? new HashSet<Guid>();
            var layerNames = (p["layers"] as JArray)?
                .Select(t => t?.ToString() ?? "")
                .Where(n => !string.IsNullOrEmpty(n))
                .ToHashSet() ?? new HashSet<string>();

            var allowedLayerIdx = new HashSet<int>();
            foreach (var ln in layerNames)
            {
                var idx = Doc.Layers.FindByFullPath(ln, -1);
                if (idx >= 0) allowedLayerIdx.Add(idx);
            }

            var prevHidden = new List<Guid>();
            var prevSelected = Doc.Objects.GetSelectedObjects(false, false)
                .Select(o => o.Id).ToList();

            try
            {
                Doc.Objects.UnselectAll();
                bool isTargeted = selectionIds.Count > 0 || allowedLayerIdx.Count > 0;
                foreach (var obj in Doc.Objects.GetObjectList(ObjectType.AnyObject))
                {
                    var inSelection = selectionIds.Contains(obj.Id);
                    var onLayer = allowedLayerIdx.Contains(obj.Attributes.LayerIndex);
                    var isTarget = inSelection || onLayer;

                    if (!isTargeted) continue;
                    if (isTarget)
                    {
                        Doc.Objects.Select(obj.Id, true);
                    }
                    else if (!ghostOthers)
                    {
                        if (obj.IsHidden) continue;
                        if (Doc.Objects.Hide(obj.Id, true))
                            prevHidden.Add(obj.Id);
                    }
                }

                if (isTargeted && zoomToSelection)
                {
                    SafeRunScript("_Zoom _Selected", "ViewportPreview");
                }

                SafeRunScript(
                    $"_-ViewCaptureToFile \"{path}\" _Width={width} _Height={height} _Enter",
                    "ViewportPreview");
            }
            finally
            {
                foreach (var id in prevHidden)
                {
                    Doc.Objects.Show(id, true);
                }
                Doc.Objects.UnselectAll();
                foreach (var id in prevSelected)
                {
                    Doc.Objects.Select(id, true);
                }
                Doc.Views.Redraw();
            }

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["path"] = path,
                    ["width"] = width,
                    ["height"] = height,
                    ["selection_count"] = selectionIds.Count,
                    ["layer_count"] = layerNames.Count,
                    ["ghost_others"] = ghostOthers,
                    ["zoom_to_selection"] = zoomToSelection,
                },
                ["text"] = $"Viewport preview captured to {path}.",
            };
        }
    }

    public class ObjectHandler : HandlerBase
    {
        public JObject Delete(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            foreach (var id in ids) Doc.Objects.Delete(id, true);
            Doc.Views.Redraw();
            return StatusOk($"Deleted {ids.Count} objects");
        }

        public JObject Select(JObject p)
        {
            var deselectFirst = p["deselect_first"]?.Value<bool>() ?? true;
            if (deselectFirst)
                Doc.Objects.UnselectAll();

            var explicitIds = p["object_ids"];
            var namePattern = p["name_pattern"]?.ToString();
            var layerFilter = p["layer"]?.ToString();
            var typeFilter = p["object_type"]?.ToString();
            var colorTok = p["color"] as Newtonsoft.Json.Linq.JArray;
            var userText = p["user_text"] as JObject;

            System.Drawing.Color? requestedColor = null;
            if (colorTok != null && colorTok.Count >= 3)
            {
                requestedColor = System.Drawing.Color.FromArgb(
                    colorTok[0].Value<int>(), colorTok[1].Value<int>(), colorTok[2].Value<int>());
            }

            System.Text.RegularExpressions.Regex? nameRegex = null;
            if (!string.IsNullOrEmpty(namePattern))
                nameRegex = GlobToRegex(namePattern);

            IEnumerable<Rhino.DocObjects.RhinoObject> candidates;
            if (explicitIds != null && explicitIds.Type == Newtonsoft.Json.Linq.JTokenType.Array)
            {
                var idList = new List<Rhino.DocObjects.RhinoObject>();
                foreach (var t in explicitIds)
                {
                    var obj = Doc.Objects.FindId(FindId(t.ToString()));
                    if (obj == null)
                        throw new KeyNotFoundException($"Object not found: {t}");
                    idList.Add(obj);
                }
                candidates = idList;
            }
            else
            {
                candidates = Doc.Objects.Where(o => !o.IsDeleted);
            }

            var matched = new List<System.Guid>();
            foreach (var obj in candidates)
            {
                if (!string.IsNullOrEmpty(layerFilter))
                {
                    var lay = Doc.Layers.FindIndex(obj.Attributes.LayerIndex);
                    if (lay == null || lay.Name != layerFilter) continue;
                }
                if (nameRegex != null && !nameRegex.IsMatch(obj.Attributes.Name ?? ""))
                    continue;
                if (requestedColor.HasValue)
                {
                    var c = obj.Attributes.ObjectColor;
                    if (c.R != requestedColor.Value.R || c.G != requestedColor.Value.G || c.B != requestedColor.Value.B)
                        continue;
                }
                if (!string.IsNullOrEmpty(typeFilter) &&
                    !obj.Geometry.ObjectType.ToString().Equals(typeFilter, StringComparison.OrdinalIgnoreCase))
                    continue;
                if (userText != null)
                {
                    var ok = true;
                    foreach (var prop in userText.Properties())
                    {
                        var got = obj.Attributes.GetUserString(prop.Name);
                        if (got != prop.Value.ToString()) { ok = false; break; }
                    }
                    if (!ok) continue;
                }

                obj.Select(true);
                matched.Add(obj.Id);
            }

            Doc.Views.Redraw();
            return new JObject
            {
                ["status"] = "ok",
                ["summary"] = new JObject
                {
                    ["count"] = matched.Count,
                    ["object_ids"] = new Newtonsoft.Json.Linq.JArray(matched.Select(g => g.ToString())),
                },
                ["text"] = $"Selected {matched.Count} objects",
            };
        }

        private static System.Text.RegularExpressions.Regex GlobToRegex(string pattern)
        {
            var sb = new System.Text.StringBuilder("^");
            foreach (var ch in pattern)
            {
                if (ch == '*') sb.Append(".*");
                else if (ch == '?') sb.Append('.');
                else sb.Append(System.Text.RegularExpressions.Regex.Escape(ch.ToString()));
            }
            sb.Append('$');
            return new System.Text.RegularExpressions.Regex(sb.ToString());
        }

        public JObject MoveToLayer(JObject p)
        {
            var layerName = p["layer"]!.ToString();
            var idx = Doc.Layers.FindByFullPath(layerName, -1);
            if (idx < 0) throw new KeyNotFoundException($"Layer not found: {layerName}");
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj == null) continue;
                var attrs = obj.Attributes;
                attrs.LayerIndex = idx;
                Doc.Objects.ModifyAttributes(obj, attrs, true);
            }
            return StatusOk($"Moved {ids.Count} objects to layer '{layerName}'");
        }

        public JObject BlockCreate(JObject p)
        {
            SafeRunScript("_Block", nameof(BlockCreate));
            return StatusOk("Block created");
        }

        public JObject BlockInsert(JObject p)
        {
            var name = p["name"]?.ToString();
            if (string.IsNullOrWhiteSpace(name))
                throw new System.ArgumentException("BlockInsert requires 'name'.");
            if (name.Contains('"'))
                throw new System.ArgumentException("BlockInsert 'name' must not contain double-quote characters.");
            SafeRunScript($"_-Insert \"{name}\" _Enter", nameof(BlockInsert));
            return StatusOk($"Block inserted: {name}");
        }

        public JObject GroupCreate(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var name = p["name"]?.ToString();
            var groupIdx = string.IsNullOrEmpty(name)
                ? Doc.Groups.Add(ids)
                : Doc.Groups.Add(name, ids);
            return new JObject
            {
                ["summary"] = new JObject { ["group_index"] = groupIdx },
                ["text"] = $"Group created with {ids.Count} objects"
            };
        }
    }
}

using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// BIM interchange — IFC + gbXML round-trip and IFC PropertySet metadata.
    /// Conversion uses Rhino 8's bundled IFC import/export (via _-Export and
    /// _-Import script aliases) so behaviour matches the GUI dialogs the user
    /// already trusts.
    /// </summary>
    public class BimIoHandler : HandlerBase
    {
        public JObject ExportIfc(JObject p)
        {
            var path = p["path"]!.ToString();
            var schema = p["schema_version"]?.ToString() ?? "IFC4";
            var projectName = p["project_name"]?.ToString() ?? "rhino-mcp export";
            var entityMap = p["entity_type_map"] as JObject;

            // Tag objects with the requested entity_type before invoking the
            // IFC exporter so the resulting file carries IfcWall / IfcSlab /
            // ... rather than every shape ending up as IfcBuildingElementProxy.
            if (entityMap != null)
            {
                var idsTok = p["object_ids"] as JArray;
                IEnumerable<RhinoObject> targets =
                    idsTok != null
                        ? idsTok.Select(t => Doc.Objects.FindId(FindId(t.ToString()))).Where(o => o != null)!
                        : Doc.Objects.Cast<RhinoObject>();
                foreach (var obj in targets)
                {
                    var fn = obj.Attributes.GetUserString("function") ?? "";
                    if (string.IsNullOrEmpty(fn)) continue;
                    var entity = entityMap[fn]?.ToString();
                    if (string.IsNullOrEmpty(entity)) continue;
                    obj.Attributes.SetUserString("ifc_entity", entity);
                    Doc.Objects.ModifyAttributes(obj, obj.Attributes, true);
                }
            }

            // Set the IFC project name as a document user-string the exporter
            // picks up (matches the dialog's "Project name" field).
            Doc.Strings.SetString("ifc_project_name", projectName);
            Doc.Strings.SetString("ifc_schema", schema);

            SafeRunScript($"_-Export \"{path}\" _Enter");
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["path"] = path,
                    ["schema_version"] = schema,
                    ["project_name"] = projectName,
                },
                ["text"] = $"IFC ({schema}) exported to {path}",
            };
        }

        public JObject ImportIfc(JObject p)
        {
            var path = p["path"]!.ToString();
            var rootLayer = p["target_layer_root"]?.ToString() ?? "BIM";
            var rootIdx = Doc.Layers.FindByFullPath(rootLayer, -1);
            if (rootIdx < 0) rootIdx = Doc.Layers.Add(new Layer { Name = rootLayer });

            int before = Doc.Objects.Count;
            SafeRunScript($"_-Import \"{path}\" _Enter");
            int after = Doc.Objects.Count;

            // Bucket newly imported objects under <root>::<IfcType>.
            var filterArr = p["filter_by_type"] as JArray;
            var allow = filterArr?.Select(t => t.ToString()).ToHashSet();
            int kept = 0;
            int filtered = 0;
            foreach (var obj in Doc.Objects.Cast<RhinoObject>().Skip(before))
            {
                var entity = obj.Attributes.GetUserString("ifc_entity") ?? "IfcBuildingElement";
                if (allow != null && !allow.Contains(entity))
                {
                    Doc.Objects.Delete(obj.Id, true);
                    filtered++;
                    continue;
                }
                var leaf = $"{rootLayer}::{entity}";
                var leafIdx = Doc.Layers.FindByFullPath(leaf, -1);
                if (leafIdx < 0)
                {
                    var layer = new Layer { Name = entity, ParentLayerId = Doc.Layers[rootIdx].Id };
                    leafIdx = Doc.Layers.Add(layer);
                }
                var attrs = obj.Attributes;
                attrs.LayerIndex = leafIdx;
                Doc.Objects.ModifyAttributes(obj, attrs, true);
                kept++;
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["path"] = path,
                    ["imported_count"] = kept,
                    ["filtered_out"] = filtered,
                    ["target_layer_root"] = rootLayer,
                },
                ["text"] = $"IFC import: {kept} object(s) retained, {filtered} filtered.",
            };
        }

        public JObject ExportGbXml(JObject p)
        {
            var path = p["path"]!.ToString();
            // gbXML export depends on the gbXML add-in. We delegate to the
            // generic export script which routes by extension.
            SafeRunScript($"_-Export \"{path}\" _Enter");
            return new JObject
            {
                ["summary"] = new JObject { ["path"] = path },
                ["text"] = $"gbXML exported to {path}",
            };
        }

        public JObject MetadataSet(JObject p)
        {
            var ids = p["object_ids"]!.Select(t => FindId(t.ToString())).ToList();
            var entity = p["entity_type"]!.ToString();
            var pset = p["pset_name"]?.ToString() ?? "Pset_RhinoMcp";
            var props = p["properties"] as JObject ?? new JObject();
            int applied = 0;
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj == null) continue;
                var attrs = obj.Attributes;
                attrs.SetUserString("ifc_entity", entity);
                attrs.SetUserString("ifc_pset", pset);
                foreach (var prop in props.Properties())
                {
                    attrs.SetUserString($"{pset}::{prop.Name}", prop.Value.ToString());
                }
                Doc.Objects.ModifyAttributes(obj, attrs, true);
                applied++;
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_ids"] = new JArray(ids.Select(g => g.ToString()).Cast<object>().ToArray()),
                    ["entity_type"] = entity,
                    ["pset_name"] = pset,
                    ["property_count"] = props.Count,
                },
                ["text"] = $"Tagged {applied} object(s) as {entity}",
            };
        }

        // ── PropertySet read/write ──────────────────────────────────────────────
        // Properties are persisted on the object's UserString table under the
        // key "<pset_name>::<key>" so values survive a Save/Load cycle and the
        // existing IFC export path picks them up automatically.

        public JObject PsetGet(JObject p)
        {
            var id = FindId(p["object_id"]!.ToString());
            var obj = Doc.Objects.FindId(id)
                ?? throw new KeyNotFoundException($"Object {id} not found.");
            var psetFilter = p["pset_name"]?.ToString();

            var groups = new JObject();
            int total = 0;
            foreach (var key in obj.Attributes.GetUserStrings().AllKeys)
            {
                if (string.IsNullOrEmpty(key) || !key.Contains("::")) continue;
                var split = key.Split(new[] { "::" }, 2, System.StringSplitOptions.None);
                var psetName = split[0];
                var propName = split[1];
                if (!string.IsNullOrEmpty(psetFilter) && psetName != psetFilter) continue;
                var bucket = (groups[psetName] as JObject) ?? new JObject();
                bucket[propName] = obj.Attributes.GetUserString(key);
                groups[psetName] = bucket;
                total++;
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_id"] = id.ToString(),
                    ["entity_type"] = obj.Attributes.GetUserString("ifc_entity") ?? "",
                    ["property_count"] = total,
                    ["pset_count"] = groups.Count,
                },
                ["psets"] = groups,
                ["text"] = $"Read {total} properties across {groups.Count} PropertySet(s).",
            };
        }

        public JObject PsetSet(JObject p)
        {
            var id = FindId(p["object_id"]!.ToString());
            var obj = Doc.Objects.FindId(id)
                ?? throw new KeyNotFoundException($"Object {id} not found.");
            var pset = p["pset_name"]?.ToString();
            if (string.IsNullOrWhiteSpace(pset))
                throw new System.ArgumentException("'pset_name' is required.");
            var props = p["properties"] as JObject
                ?? throw new System.ArgumentException("'properties' must be a JSON object.");
            var replace = p["replace_existing"]?.Value<bool>() ?? false;

            var attrs = obj.Attributes;
            if (replace)
            {
                foreach (var k in attrs.GetUserStrings().AllKeys)
                {
                    if (!string.IsNullOrEmpty(k) && k.StartsWith($"{pset}::"))
                        attrs.SetUserString(k, null);
                }
            }
            int written = 0;
            foreach (var prop in props.Properties())
            {
                attrs.SetUserString($"{pset}::{prop.Name}", prop.Value.ToString());
                written++;
            }
            Doc.Objects.ModifyAttributes(obj, attrs, true);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_id"] = id.ToString(),
                    ["pset_name"] = pset,
                    ["property_count"] = written,
                    ["replace_existing"] = replace,
                },
                ["text"] = $"Wrote {written} properties under {pset}.",
            };
        }

        public JObject PsetDelete(JObject p)
        {
            var id = FindId(p["object_id"]!.ToString());
            var obj = Doc.Objects.FindId(id)
                ?? throw new KeyNotFoundException($"Object {id} not found.");
            var pset = p["pset_name"]?.ToString();
            if (string.IsNullOrWhiteSpace(pset))
                throw new System.ArgumentException("'pset_name' is required.");

            var attrs = obj.Attributes;
            int removed = 0;
            foreach (var k in attrs.GetUserStrings().AllKeys.ToArray())
            {
                if (!string.IsNullOrEmpty(k) && k.StartsWith($"{pset}::"))
                {
                    attrs.SetUserString(k, null);
                    removed++;
                }
            }
            Doc.Objects.ModifyAttributes(obj, attrs, true);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_id"] = id.ToString(),
                    ["pset_name"] = pset,
                    ["removed_count"] = removed,
                },
                ["text"] = $"Removed {removed} properties under {pset}.",
            };
        }
    }
}

using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMCPBridge.Handlers
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

            RhinoApp.RunScript($"_-Export \"{path}\" _Enter", false);
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
            RhinoApp.RunScript($"_-Import \"{path}\" _Enter", false);
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
            RhinoApp.RunScript($"_-Export \"{path}\" _Enter", false);
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
    }
}

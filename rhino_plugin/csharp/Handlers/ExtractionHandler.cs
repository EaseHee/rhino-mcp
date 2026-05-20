using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Curve extraction: duplicate edges, borders, isocurves, Make2D.
    /// </summary>
    public class ExtractionHandler : HandlerBase
    {
        public JObject DupEdge(JObject p)
        {
            var brep = FindBrep(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Brep not found");
            var edgeIndices = p["edge_indices"] as JArray;

            uint undo = Doc.BeginUndoRecord("MCP: dup_edge");
            try
            {
                Curve[] edges;
                if (edgeIndices != null && edgeIndices.Count > 0)
                {
                    var selected = new List<Curve>();
                    foreach (var idx in edgeIndices)
                    {
                        int i = idx.Value<int>();
                        if (i >= 0 && i < brep.Edges.Count)
                            selected.Add(brep.Edges[i].DuplicateCurve());
                    }
                    edges = selected.ToArray();
                }
                else
                {
                    edges = brep.DuplicateEdgeCurves();
                }

                var ids = new JArray();
                var layerName = p["layer"]?.ToString();
                foreach (var crv in edges)
                {
                    Guid id;
                    if (!string.IsNullOrEmpty(layerName))
                    {
                        var pp = new JObject { ["layer"] = layerName };
                        id = AddObject(crv, pp);
                    }
                    else
                    {
                        id = Doc.Objects.AddCurve(crv);
                    }
                    ids.Add(id.ToString());
                }

                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject { ["object_ids"] = ids },
                    ["text"] = $"Extracted {ids.Count} edge curve(s)"
                };
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject DupBorder(JObject p)
        {
            var brep = FindBrep(p["object_id"]!.ToString());
            var mesh = brep == null ? FindMesh(p["object_id"]!.ToString()) : null;
            if (brep == null && mesh == null)
                throw new ArgumentException("Surface or mesh not found");

            string borderType = p["border_type"]?.ToString() ?? "all";

            uint undo = Doc.BeginUndoRecord("MCP: dup_border");
            try
            {
                Curve[]? curves = null;
                if (brep != null)
                {
                    curves = borderType.ToLower() switch
                    {
                        "naked" => brep.DuplicateNakedEdgeCurves(true, false),
                        "interior" => brep.DuplicateNakedEdgeCurves(false, true),
                        _ => brep.DuplicateNakedEdgeCurves(true, true),
                    };
                }
                else if (mesh != null)
                {
                    var polylines = mesh.GetNakedEdges();
                    if (polylines != null)
                        curves = polylines.Select(pl => (Curve)new PolylineCurve(pl)).ToArray();
                }

                var ids = new JArray();
                if (curves != null)
                {
                    foreach (var crv in curves)
                    {
                        var id = Doc.Objects.AddCurve(crv);
                        ids.Add(id.ToString());
                    }
                }

                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject { ["object_ids"] = ids },
                    ["text"] = $"Extracted {ids.Count} border curve(s)"
                };
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject Isocurve(JObject p)
        {
            var srf = FindSurface(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Surface not found");
            int direction = p["direction"]?.Value<int>() ?? 0;
            double parameter = p["parameter"]!.Value<double>();

            uint undo = Doc.BeginUndoRecord("MCP: isocurve");
            try
            {
                var iso = srf.IsoCurve(direction, parameter);
                if (iso == null)
                    throw new InvalidOperationException("Isocurve extraction failed");

                var id = Doc.Objects.AddCurve(iso);
                Doc.Views.Redraw();
                return ObjectResult(id, "Curve");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject Make2D(JObject p)
        {
            var ids = (p["object_ids"] as JArray)
                ?? throw new ArgumentException("object_ids required");

            uint undo = Doc.BeginUndoRecord("MCP: make2d");
            try
            {
                // Select the objects first
                EmitProgress(0, ids.Count, $"Make2D: selecting {ids.Count} object(s)");
                int selected = 0;
                foreach (var id in ids)
                {
                    selected++;
                    var obj = FindObject(id.ToString());
                    if (obj != null) obj.Select(true);
                    if (selected % 50 == 0 || selected == ids.Count)
                        EmitProgress(selected, ids.Count, $"Make2D: selected {selected}/{ids.Count}");
                }

                bool showHidden = p["show_hidden"]?.Value<bool>() ?? false;
                string hiddenOpt = showHidden ? "_Yes" : "_No";
                string cmd = $"_-Make2D _ShowHiddenLines={hiddenOpt} _Enter";
                EmitProgress(null, null, "Make2D: running command (no intermediate progress)");
                SafeRunScript(cmd);

                Doc.Objects.UnselectAll();
                Doc.Views.Redraw();

                return StatusOk("Make2D completed");
            }
            finally { Doc.EndUndoRecord(undo); }
        }
    }
}

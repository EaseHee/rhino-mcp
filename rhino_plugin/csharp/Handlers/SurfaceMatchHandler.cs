using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    /// <summary>Surface matching: match, blend, merge.</summary>
    public class SurfaceMatchHandler : HandlerBase
    {
        public JObject Match(JObject p)
        {
            var srf = FindSurface(p["surface_id"]!.ToString())
                ?? throw new ArgumentException("Source surface not found");
            var target = FindSurface(p["target_id"]!.ToString())
                ?? throw new ArgumentException("Target surface not found");
            int continuity = p["continuity"]?.Value<int>() ?? 2;

            uint undo = Doc.BeginUndoRecord("MCP: match_surface");
            try
            {
                var srcId = p["surface_id"]!.ToString();
                var tgtId = p["target_id"]!.ToString();
                string cmd = $"_-MatchSrf _SelId {srcId} _Enter _SelId {tgtId} _Enter " +
                    $"_Continuity={continuity} _Enter";
                RhinoApp.RunScript(cmd, false);
                Doc.Views.Redraw();

                return new JObject
                {
                    ["summary"] = new JObject
                    {
                        ["surface_id"] = srcId,
                        ["target_id"] = tgtId,
                        ["continuity"] = continuity
                    },
                    ["text"] = $"MatchSrf applied (continuity G{continuity})"
                };
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject Blend(JObject p)
        {
            var edge1 = FindObject(p["edge_id_1"]!.ToString())
                ?? throw new ArgumentException("First edge/surface not found");
            var edge2 = FindObject(p["edge_id_2"]!.ToString())
                ?? throw new ArgumentException("Second edge/surface not found");

            uint undo = Doc.BeginUndoRecord("MCP: blend_surface");
            try
            {
                string cmd = $"_-BlendSrf _SelId {edge1.Id} _Enter _SelId {edge2.Id} _Enter _Enter";
                RhinoApp.RunScript(cmd, false);
                Doc.Views.Redraw();

                return new JObject
                {
                    ["summary"] = new JObject
                    {
                        ["edge_id_1"] = edge1.Id.ToString(),
                        ["edge_id_2"] = edge2.Id.ToString()
                    },
                    ["text"] = "BlendSrf created"
                };
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject Merge(JObject p)
        {
            var ids = (p["surface_ids"] as JArray)
                ?? throw new ArgumentException("surface_ids required");

            uint undo = Doc.BeginUndoRecord("MCP: merge_surfaces");
            try
            {
                string selCmd = string.Join(" ", ids.Select(id => $"_SelId {id}"));
                string cmd = $"_-MergeSrf {selCmd} _Enter _Enter";
                RhinoApp.RunScript(cmd, false);
                Doc.Views.Redraw();

                return new JObject
                {
                    ["summary"] = new JObject
                    {
                        ["surface_count"] = ids.Count
                    },
                    ["text"] = $"Merged {ids.Count} surface(s)"
                };
            }
            finally { Doc.EndUndoRecord(undo); }
        }
    }
}

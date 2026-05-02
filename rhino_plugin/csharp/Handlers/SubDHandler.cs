using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMCPBridge.Handlers
{
    /// <summary>SubD operations: create from mesh, convert to NURBS.</summary>
    public class SubDHandler : HandlerBase
    {
        public JObject Create(JObject p)
        {
            var mesh = FindMesh(p["mesh_id"]!.ToString())
                ?? throw new ArgumentException("Mesh not found");

            uint undo = Doc.BeginUndoRecord("MCP: subd_create");
            try
            {
                var subd = SubD.CreateFromMesh(mesh);
                if (subd == null)
                    throw new InvalidOperationException("SubD creation from mesh failed");

                var id = AddObject(subd, p);
                Doc.Views.Redraw();
                return ObjectResult(id, "SubD");
            }
            finally { Doc.EndUndoRecord(undo); }
        }

        public JObject ToNurbs(JObject p)
        {
            var obj = FindObject(p["object_id"]!.ToString())
                ?? throw new ArgumentException("Object not found");
            var geom = obj.Geometry;

            if (geom is not SubD subd)
                throw new ArgumentException("Object is not a SubD");

            uint undo = Doc.BeginUndoRecord("MCP: subd_to_nurbs");
            try
            {
                var brep = subd.ToBrep(SubDToBrepOptions.Default);
                if (brep == null)
                    throw new InvalidOperationException("SubD to NURBS conversion failed");

                var id = AddObject(brep, p);
                Doc.Views.Redraw();
                return ObjectResult(id, "Brep");
            }
            finally { Doc.EndUndoRecord(undo); }
        }
    }
}

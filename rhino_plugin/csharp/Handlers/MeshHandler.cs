using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMcp.Handlers
{
    public class MeshHandler : HandlerBase
    {
        public JObject Box(JObject p)
        {
            var corner = ToPoint(p["corner"]!);
            var sx = p["size_x"]!.Value<double>();
            var sy = p["size_y"]!.Value<double>();
            var sz = p["size_z"]!.Value<double>();
            var box = new BoundingBox(corner, new Point3d(corner.X + sx, corner.Y + sy, corner.Z + sz));
            var mesh = Mesh.CreateFromBox(box, 1, 1, 1);
            var id = AddObject(mesh, p);
            return ObjectResult(id, "MeshBox");
        }

        public JObject FromBrep(JObject p)
        {
            var brep = FindBrep(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Brep not found");
            var mp = MeshingParameters.Default;
            var meshes = Mesh.CreateFromBrep(brep, mp);
            if (meshes == null || meshes.Length == 0)
                throw new InvalidOperationException("Meshing failed");
            var joined = new Mesh();
            foreach (var m in meshes) joined.Append(m);
            var id = AddObject(joined, p);
            return ObjectResult(id, "MeshFromBrep");
        }

        public JObject FromSurface(JObject p)
        {
            var srf = FindSurface(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Surface not found");
            var mp = MeshingParameters.Default;
            var mesh = Mesh.CreateFromSurface(srf, mp);
            if (mesh == null) throw new InvalidOperationException("Meshing failed");
            var id = AddObject(mesh, p);
            return ObjectResult(id, "MeshFromSurface");
        }

        public JObject BooleanUnion(JObject p)
        {
            var meshes = p["object_ids"]!.Select(t =>
                FindMesh(t.ToString()) ?? throw new KeyNotFoundException($"Mesh not found: {t}")
            ).ToArray();
            var result = Mesh.CreateBooleanUnion(meshes);
            if (result == null || result.Length == 0)
                throw new InvalidOperationException("Mesh boolean union failed");
            var id = AddObject(result[0], p);
            return ObjectResult(id, "MeshBooleanUnion");
        }

        public JObject BooleanDifference(JObject p)
        {
            var a = p["a_ids"]!.Select(t =>
                FindMesh(t.ToString()) ?? throw new KeyNotFoundException($"Mesh not found: {t}")
            ).ToArray();
            var b = p["b_ids"]!.Select(t =>
                FindMesh(t.ToString()) ?? throw new KeyNotFoundException($"Mesh not found: {t}")
            ).ToArray();
            var result = Mesh.CreateBooleanDifference(a, b);
            if (result == null || result.Length == 0)
                throw new InvalidOperationException("Mesh boolean difference failed");
            var id = AddObject(result[0], p);
            return ObjectResult(id, "MeshBooleanDifference");
        }

        public JObject Weld(JObject p)
        {
            var mesh = FindMesh(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Mesh not found");
            var angle = RhinoMath.ToRadians(p["angle_degrees"]?.Value<double>() ?? 22.5);
            mesh.Weld(angle);
            var id = AddObject(mesh, p);
            return ObjectResult(id, "MeshWeld");
        }

        public JObject Unweld(JObject p)
        {
            var mesh = FindMesh(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Mesh not found");
            var angle = RhinoMath.ToRadians(p["angle_degrees"]?.Value<double>() ?? 22.5);
            mesh.Unweld(angle, true);
            var id = AddObject(mesh, p);
            return ObjectResult(id, "MeshUnweld");
        }

        public JObject Reduce(JObject p)
        {
            var mesh = FindMesh(p["object_id"]!.ToString())
                ?? throw new KeyNotFoundException("Mesh not found");
            var targetCount = p["target_count"]!.Value<int>();
            mesh.Reduce(targetCount, true, 3, true);
            var id = AddObject(mesh, p);
            return ObjectResult(id, "MeshReduce");
        }
    }
}

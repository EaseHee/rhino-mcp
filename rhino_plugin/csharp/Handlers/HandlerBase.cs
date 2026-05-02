using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;

namespace RhinoMCPBridge.Handlers
{
    /// <summary>
    /// Shared utilities for all command handlers.
    /// </summary>
    public abstract class HandlerBase
    {
        protected static RhinoDoc Doc => RhinoDoc.ActiveDoc;

        protected static Point3d ToPoint(JToken tok)
        {
            return new Point3d(
                tok["x"]?.Value<double>() ?? 0,
                tok["y"]?.Value<double>() ?? 0,
                tok["z"]?.Value<double>() ?? 0);
        }

        protected static Vector3d ToVector(JToken tok)
        {
            return new Vector3d(
                tok["x"]?.Value<double>() ?? 0,
                tok["y"]?.Value<double>() ?? 0,
                tok["z"]?.Value<double>() ?? 0);
        }

        protected static Plane ToPlane(JToken? tok)
        {
            if (tok == null) return Plane.WorldXY;
            var origin = ToPoint(tok["origin"] ?? JObject.FromObject(new { x = 0, y = 0, z = 0 }));
            return new Plane(origin, Vector3d.ZAxis);
        }

        protected static Guid FindId(string guidStr)
        {
            return Guid.Parse(guidStr);
        }

        protected static RhinoObject? FindObject(string guidStr)
        {
            var id = FindId(guidStr);
            return Doc.Objects.FindId(id);
        }

        protected static GeometryBase? FindGeometry(string guidStr)
        {
            return FindObject(guidStr)?.Geometry;
        }

        protected static Curve? FindCurve(string guidStr)
        {
            return FindGeometry(guidStr) as Curve;
        }

        protected static Brep? FindBrep(string guidStr)
        {
            var geom = FindGeometry(guidStr);
            if (geom is Brep brep) return brep;
            if (geom is Extrusion ext) return ext.ToBrep();
            return null;
        }

        protected static Surface? FindSurface(string guidStr)
        {
            var geom = FindGeometry(guidStr);
            if (geom is Surface srf) return srf;
            if (geom is Brep brep && brep.Faces.Count == 1) return brep.Faces[0];
            return null;
        }

        protected static Mesh? FindMesh(string guidStr)
        {
            return FindGeometry(guidStr) as Mesh;
        }

        /// <summary>Add geometry to the document with optional layer/name attributes.</summary>
        protected static Guid AddObject(GeometryBase geometry, JObject parameters)
        {
            var attrs = new ObjectAttributes();

            var layerName = parameters["layer"]?.ToString();
            if (!string.IsNullOrEmpty(layerName))
            {
                var layerIndex = Doc.Layers.FindByFullPath(layerName, -1);
                if (layerIndex < 0)
                {
                    var layer = new Layer { Name = layerName };
                    layerIndex = Doc.Layers.Add(layer);
                }
                attrs.LayerIndex = layerIndex;
            }

            var name = parameters["name"]?.ToString();
            if (!string.IsNullOrEmpty(name))
                attrs.Name = name;

            var id = Doc.Objects.Add(geometry, attrs);
            Doc.Views.Redraw();
            return id;
        }

        /// <summary>Standard success response with object_id and kind.</summary>
        protected static JObject ObjectResult(Guid id, string kind)
        {
            var obj = Doc.Objects.FindId(id);
            var bbox = obj?.Geometry.GetBoundingBox(true) ?? BoundingBox.Empty;

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_id"] = id.ToString(),
                    ["kind"] = kind,
                    ["bbox"] = new JObject
                    {
                        ["min"] = new JObject { ["x"] = bbox.Min.X, ["y"] = bbox.Min.Y, ["z"] = bbox.Min.Z },
                        ["max"] = new JObject { ["x"] = bbox.Max.X, ["y"] = bbox.Max.Y, ["z"] = bbox.Max.Z }
                    }
                },
                ["text"] = $"{kind} created: {id}"
            };
        }

        protected static JObject StatusOk(string message = "ok")
        {
            return new JObject { ["status"] = message };
        }
    }
}

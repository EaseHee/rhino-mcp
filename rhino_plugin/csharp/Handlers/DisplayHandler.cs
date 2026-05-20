using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMcp.Handlers
{
    public class DisplayHandler : HandlerBase
    {
        public JObject ViewSet(JObject p)
        {
            var name = p["name"]!.ToString();
            SafeRunScript($"_-SetView _World _{name}");
            return StatusOk($"View set to {name}");
        }

        public JObject ZoomExtent(JObject p)
        {
            SafeRunScript("_Zoom _Extents");
            return StatusOk("Zoomed to extents");
        }

        public JObject NamedViewSave(JObject p)
        {
            var name = p["name"]!.ToString();
            SafeRunScript($"_-NamedView _Save \"{name}\" _Enter");
            return StatusOk($"Named view saved: {name}");
        }

        public JObject ModeSet(JObject p)
        {
            var mode = p["mode"]!.ToString();
            SafeRunScript($"_-SetDisplayMode _Mode={mode}");
            return StatusOk($"Display mode set to {mode}");
        }

        public JObject Turntable(JObject p)
        {
            var outputPath = p["output_path"]!.ToString();
            var frames = p["frames"]?.Value<int>() ?? 60;
            SafeRunScript($"_-Turntable _FrameCount={frames} _OutputFile=\"{outputPath}\" _Enter");
            return new JObject
            {
                ["status"] = "ok",
                ["output_path"] = outputPath,
                ["frames"] = frames
            };
        }

        public JObject RenderViewport(JObject p)
        {
            var outputPath = p["output_path"]?.ToString();
            if (!string.IsNullOrEmpty(outputPath))
                SafeRunScript($"_-Render\n_-SaveRenderWindowAs \"{outputPath}\"\n_-CloseRenderWindow");
            else
                SafeRunScript("_-Render");
            return new JObject { ["status"] = "ok", ["output_path"] = outputPath };
        }

        public JObject ZoomObject(JObject p)
        {
            var ids = (p["object_ids"] as JArray)?
                .Select(t => FindId(t.ToString()))
                .ToList() ?? new List<Guid>();
            if (ids.Count == 0)
                throw new ArgumentException("object_ids must be non-empty");

            var bbox = Rhino.Geometry.BoundingBox.Empty;
            var miss = 0;
            foreach (var id in ids)
            {
                var obj = Doc.Objects.FindId(id);
                if (obj == null) { miss++; continue; }
                bbox.Union(obj.Geometry.GetBoundingBox(true));
            }
            if (!bbox.IsValid)
                throw new InvalidOperationException("Could not compute bounding box from given ids");

            var view = Doc.Views.ActiveView ?? throw new InvalidOperationException("No active view");
            view.ActiveViewport.ZoomBoundingBox(bbox);
            view.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["zoomed"] = ids.Count - miss,
                    ["missing"] = miss,
                },
                ["text"] = $"Zoomed to {ids.Count - miss} object(s){(miss > 0 ? $" ({miss} missing)" : "")}",
            };
        }

        public JObject ZoomLayer(JObject p)
        {
            var layerName = p["layer"]!.ToString();
            var layerIdx = Doc.Layers.FindByFullPath(layerName, -1);
            if (layerIdx < 0)
                throw new KeyNotFoundException($"Layer not found: {layerName}");

            var bbox = Rhino.Geometry.BoundingBox.Empty;
            var count = 0;
            foreach (var obj in Doc.Objects)
            {
                if (obj.Attributes.LayerIndex != layerIdx) continue;
                bbox.Union(obj.Geometry.GetBoundingBox(true));
                count++;
            }
            if (count == 0)
                throw new InvalidOperationException($"Layer '{layerName}' has no objects to zoom");

            var view = Doc.Views.ActiveView ?? throw new InvalidOperationException("No active view");
            view.ActiveViewport.ZoomBoundingBox(bbox);
            view.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["layer"] = layerName,
                    ["object_count"] = count,
                },
                ["text"] = $"Zoomed to {count} object(s) on layer {layerName}",
            };
        }

        public JObject CaptureViewport(JObject p)
        {
            var width = p["width"]?.Value<int>() ?? 0;
            var height = p["height"]?.Value<int>() ?? 0;
            var viewName = p["view_name"]?.ToString();
            var transparent = p["transparent_bg"]?.Value<bool>() ?? false;
            var outputPath = p["output_path"]?.ToString();

            var view = string.IsNullOrEmpty(viewName)
                ? Doc.Views.ActiveView
                : Doc.Views.FirstOrDefault(v => string.Equals(v.ActiveViewport.Name, viewName, StringComparison.OrdinalIgnoreCase));
            if (view == null)
                throw new KeyNotFoundException($"View not found: {viewName ?? "<active>"}");

            // Use the viewport's current size when caller leaves the dimensions at zero.
            var size = view.ClientRectangle.Size;
            var w = width > 0 ? width : size.Width;
            var h = height > 0 ? height : size.Height;
            if (w <= 0 || h <= 0)
                throw new InvalidOperationException("View has zero size and no width/height supplied");

            using var bitmap = view.CaptureToBitmap(new System.Drawing.Size(w, h));
            if (bitmap == null)
                throw new InvalidOperationException("CaptureToBitmap returned null");

            string resolvedPath = outputPath ?? Path.Combine(Path.GetTempPath(), $"rhino-mcp-capture-{Guid.NewGuid():N}.png");
#pragma warning disable CA1416 // System.Drawing.Common works on every Rhino 8 platform via mono/wine
            if (transparent)
                bitmap.MakeTransparent(System.Drawing.Color.White);
            bitmap.Save(resolvedPath, System.Drawing.Imaging.ImageFormat.Png);
#pragma warning restore CA1416

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["view"] = view.ActiveViewport.Name,
                    ["width"] = w,
                    ["height"] = h,
                    ["output_path"] = resolvedPath,
                    ["transparent_bg"] = transparent,
                },
                ["text"] = $"Captured {view.ActiveViewport.Name} → {resolvedPath} ({w}×{h})",
            };
        }
    }
}

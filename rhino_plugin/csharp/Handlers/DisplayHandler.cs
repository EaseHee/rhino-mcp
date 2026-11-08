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
            if (string.IsNullOrWhiteSpace(outputPath))
                outputPath = null;
            var asBase64 = p["as_base64"]?.Value<bool>() ?? false;
            var options = CaptureEncoder.ReadOptions(p);

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

            // A file is written when requested, or as the only output when no inline image is wanted.
            string? resolvedPath = outputPath
                ?? (asBase64 ? null : Path.Combine(Path.GetTempPath(), $"rhino-mcp-capture-{Guid.NewGuid():N}.png"));
#pragma warning disable CA1416 // System.Drawing.Common works on every Rhino 8 platform via mono/wine
            if (transparent)
                bitmap.MakeTransparent(System.Drawing.Color.White);
            if (resolvedPath != null)
                bitmap.Save(resolvedPath, System.Drawing.Imaging.ImageFormat.Png);
#pragma warning restore CA1416

            var summary = new JObject
            {
                ["view"] = view.ActiveViewport.Name,
                ["width"] = w,
                ["height"] = h,
                ["output_path"] = resolvedPath,
                ["transparent_bg"] = transparent,
            };
            var response = new JObject
            {
                ["summary"] = summary,
                ["text"] = resolvedPath != null
                    ? $"Captured {view.ActiveViewport.Name} → {resolvedPath} ({w}×{h})"
                    : $"Captured {view.ActiveViewport.Name} ({w}×{h})",
            };
            if (asBase64)
                CaptureEncoder.Attach(response, summary, bitmap, options);
            return response;
        }
    }

    /// <summary>
    /// Downscales and encodes viewport captures for inline MCP image content.
    /// </summary>
    internal static class CaptureEncoder
    {
        internal readonly struct Options
        {
            public Options(int maxWidth, bool jpeg, int quality)
            {
                MaxWidth = maxWidth;
                Jpeg = jpeg;
                Quality = quality;
            }

            public int MaxWidth { get; }
            public bool Jpeg { get; }
            public int Quality { get; }
        }

        public static Options ReadOptions(JObject p)
        {
            var maxWidth = Math.Max(0, p["max_width"]?.Value<int>() ?? 0);
            var format = p["format"]?.ToString()?.ToLowerInvariant() ?? "png";
            if (format != "png" && format != "jpeg" && format != "jpg")
                throw new ArgumentException($"format must be 'jpeg' or 'png' (got '{format}').");
            var quality = Math.Clamp(p["jpeg_quality"]?.Value<int>() ?? 80, 1, 100);
            return new Options(maxWidth, format != "png", quality);
        }

        /// <summary>
        /// Encodes the file at <paramref name="path"/> and adds the image fields to the response.
        /// </summary>
        public static void AttachFile(JObject response, JObject summary, string path, Options options)
        {
            if (!File.Exists(path))
            {
                response["base64_error"] = $"Capture file not found: {path}";
                return;
            }
            try
            {
                // Load through a memory copy so the file handle is released immediately.
                using var stream = new MemoryStream(File.ReadAllBytes(path));
#pragma warning disable CA1416 // System.Drawing.Common works on every Rhino 8 platform via mono/wine
                using var bitmap = new System.Drawing.Bitmap(stream);
#pragma warning restore CA1416
                Attach(response, summary, bitmap, options);
            }
            catch (Exception ex)
            {
                // Keep the call alive; the caller can still read the file at the reported path.
                response["base64_error"] = ex.Message;
            }
        }

        /// <summary>
        /// Encodes <paramref name="source"/> and adds image_base64, mime and image size fields.
        /// </summary>
        public static void Attach(JObject response, JObject summary, System.Drawing.Bitmap source, Options options)
        {
            try
            {
                var (bytes, mime, w, h) = Encode(source, options);
                response["image_base64"] = Convert.ToBase64String(bytes);
                response["mime"] = mime;
                summary["mime"] = mime;
                summary["image_width"] = w;
                summary["image_height"] = h;
                summary["bytes"] = bytes.Length;
            }
            catch (Exception ex)
            {
                response["base64_error"] = ex.Message;
            }
        }

#pragma warning disable CA1416 // System.Drawing.Common works on every Rhino 8 platform via mono/wine
        private static (byte[] Bytes, string Mime, int Width, int Height) Encode(System.Drawing.Bitmap source, Options options)
        {
            var w = source.Width;
            var h = source.Height;
            if (options.MaxWidth > 0 && w > options.MaxWidth)
            {
                h = Math.Max(1, (int)Math.Round((double)h * options.MaxWidth / w));
                w = options.MaxWidth;
            }

            var needsCopy = w != source.Width || h != source.Height || options.Jpeg;
            var target = needsCopy ? Resample(source, w, h, options.Jpeg) : source;
            try
            {
                if (options.Jpeg)
                {
                    var jpeg = TryEncodeJpeg(target, options.Quality);
                    if (jpeg != null)
                        return (jpeg, "image/jpeg", w, h);
                }
                using var ms = new MemoryStream();
                target.Save(ms, System.Drawing.Imaging.ImageFormat.Png);
                return (ms.ToArray(), "image/png", w, h);
            }
            finally
            {
                if (!ReferenceEquals(target, source))
                    target.Dispose();
            }
        }

        private static System.Drawing.Bitmap Resample(System.Drawing.Bitmap source, int w, int h, bool opaque)
        {
            var format = opaque
                ? System.Drawing.Imaging.PixelFormat.Format24bppRgb
                : System.Drawing.Imaging.PixelFormat.Format32bppArgb;
            var target = new System.Drawing.Bitmap(w, h, format);
            using var g = System.Drawing.Graphics.FromImage(target);
            // JPEG has no alpha channel, so transparent pixels are flattened onto white.
            if (opaque)
                g.Clear(System.Drawing.Color.White);
            g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
            g.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighQuality;
            g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.HighQuality;
            g.DrawImage(source, new System.Drawing.Rectangle(0, 0, w, h));
            return target;
        }

        private static byte[]? TryEncodeJpeg(System.Drawing.Bitmap bitmap, int quality)
        {
            try
            {
                using var ms = new MemoryStream();
                var codec = System.Drawing.Imaging.ImageCodecInfo.GetImageEncoders()
                    .FirstOrDefault(c => c.FormatID == System.Drawing.Imaging.ImageFormat.Jpeg.Guid);
                if (codec != null)
                {
                    using var parameters = new System.Drawing.Imaging.EncoderParameters(1);
                    parameters.Param[0] = new System.Drawing.Imaging.EncoderParameter(
                        System.Drawing.Imaging.Encoder.Quality, (long)quality);
                    bitmap.Save(ms, codec, parameters);
                }
                else
                {
                    bitmap.Save(ms, System.Drawing.Imaging.ImageFormat.Jpeg);
                }
                return ms.ToArray();
            }
            catch (Exception)
            {
                // Some platform backends lack a JPEG encoder; the caller falls back to PNG.
                try
                {
                    using var ms = new MemoryStream();
                    bitmap.Save(ms, System.Drawing.Imaging.ImageFormat.Jpeg);
                    return ms.ToArray();
                }
                catch (Exception)
                {
                    return null;
                }
            }
        }
#pragma warning restore CA1416
    }
}

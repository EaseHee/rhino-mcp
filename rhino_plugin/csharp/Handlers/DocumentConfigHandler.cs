using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.Geometry;

namespace RhinoMCPBridge.Handlers
{
    /// <summary>
    /// Document hygiene — units, tolerances, base point.
    /// </summary>
    public class DocumentConfigHandler : HandlerBase
    {
        private static readonly Dictionary<string, UnitSystem> UnitsAlias = new(StringComparer.OrdinalIgnoreCase)
        {
            ["mm"] = UnitSystem.Millimeters,
            ["millimeters"] = UnitSystem.Millimeters,
            ["millimetre"] = UnitSystem.Millimeters,
            ["millimetres"] = UnitSystem.Millimeters,
            ["cm"] = UnitSystem.Centimeters,
            ["centimeters"] = UnitSystem.Centimeters,
            ["m"] = UnitSystem.Meters,
            ["meter"] = UnitSystem.Meters,
            ["meters"] = UnitSystem.Meters,
            ["metre"] = UnitSystem.Meters,
            ["metres"] = UnitSystem.Meters,
            ["km"] = UnitSystem.Kilometers,
            ["in"] = UnitSystem.Inches,
            ["inch"] = UnitSystem.Inches,
            ["inches"] = UnitSystem.Inches,
            ["ft"] = UnitSystem.Feet,
            ["feet"] = UnitSystem.Feet,
            ["yd"] = UnitSystem.Yards,
            ["yards"] = UnitSystem.Yards,
            ["mi"] = UnitSystem.Miles,
            ["miles"] = UnitSystem.Miles,
        };

        private static readonly Dictionary<UnitSystem, string> UnitsName = new()
        {
            [UnitSystem.Millimeters] = "mm",
            [UnitSystem.Centimeters] = "cm",
            [UnitSystem.Meters] = "m",
            [UnitSystem.Kilometers] = "km",
            [UnitSystem.Inches] = "in",
            [UnitSystem.Feet] = "ft",
            [UnitSystem.Yards] = "yd",
            [UnitSystem.Miles] = "mi",
        };

        public JObject UnitsGet(JObject _)
        {
            var u = Doc.ModelUnitSystem;
            var name = UnitsName.TryGetValue(u, out var s) ? s : u.ToString();
            return new JObject
            {
                ["summary"] = new JObject { ["units"] = name },
                ["text"] = $"Document units: {name}",
            };
        }

        public JObject UnitsSet(JObject p)
        {
            var name = p["units"]!.ToString();
            if (!UnitsAlias.TryGetValue(name, out var target))
                throw new ArgumentException($"unknown unit '{name}'");
            var scale = p["scale_existing"]?.Value<bool>() ?? false;
            Doc.AdjustModelUnitSystem(target, scale);
            var resolvedName = UnitsName.TryGetValue(target, out var s) ? s : target.ToString();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["units"] = resolvedName,
                    ["scaled"] = scale,
                },
                ["text"] = $"Units -> {resolvedName} (scaled={scale})",
            };
        }

        public JObject ToleranceGet(JObject _)
        {
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["absolute"] = Doc.ModelAbsoluteTolerance,
                    ["angle_degrees"] = Doc.ModelAngleToleranceDegrees,
                    ["relative"] = Doc.ModelRelativeTolerance,
                },
                ["text"] = $"abs={Doc.ModelAbsoluteTolerance}, angle={Doc.ModelAngleToleranceDegrees}, rel={Doc.ModelRelativeTolerance}",
            };
        }

        public JObject ToleranceSet(JObject p)
        {
            var abs = p["absolute"]!.Value<double>();
            var angDeg = p["angle_degrees"]!.Value<double>();
            Doc.ModelAbsoluteTolerance = abs;
            Doc.ModelAngleToleranceRadians = RhinoMath.ToRadians(angDeg);
            if (p["relative"] != null && p["relative"]!.Type != JTokenType.Null)
                Doc.ModelRelativeTolerance = p["relative"]!.Value<double>();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["absolute"] = Doc.ModelAbsoluteTolerance,
                    ["angle_degrees"] = Doc.ModelAngleToleranceDegrees,
                    ["relative"] = Doc.ModelRelativeTolerance,
                },
                ["text"] = "Tolerances updated",
            };
        }

        // Base point is stored as a document user string (key below). RhinoCommon
        // does not expose a single ``ModelBasePoint`` property across all Rhino 8
        // builds; document strings are stable and round-trip through `.3dm` saves.
        private const string BasePointKey = "rhino_mcp::base_point";

        private static Point3d GetStoredBasePoint()
        {
            var raw = Doc.Strings.GetValue(BasePointKey);
            if (string.IsNullOrEmpty(raw)) return Point3d.Origin;
            var parts = raw.Split(',');
            if (parts.Length != 3) return Point3d.Origin;
            if (!double.TryParse(parts[0], out var x)) return Point3d.Origin;
            if (!double.TryParse(parts[1], out var y)) return Point3d.Origin;
            if (!double.TryParse(parts[2], out var z)) return Point3d.Origin;
            return new Point3d(x, y, z);
        }

        public JObject OriginSet(JObject p)
        {
            var pt = ToPoint(p["base_point"]!);
            var mode = p["mode"]?.ToString() ?? "reference";
            if (mode != "reference" && mode != "translate")
                throw new ArgumentException("mode must be 'reference' or 'translate'");

            if (mode == "translate")
            {
                var shift = Transform.Translation(new Vector3d(-pt.X, -pt.Y, -pt.Z));
                foreach (var obj in Doc.Objects)
                {
                    Doc.Objects.Transform(obj.Id, shift, true);
                }
                pt = new Point3d(0, 0, 0);
            }
            Doc.Strings.SetString(BasePointKey, $"{pt.X},{pt.Y},{pt.Z}");
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["base_point"] = new JObject { ["x"] = pt.X, ["y"] = pt.Y, ["z"] = pt.Z },
                    ["mode"] = mode,
                },
                ["text"] = $"Base point set ({mode})",
            };
        }

        public JObject Settings(JObject _)
        {
            var u = Doc.ModelUnitSystem;
            var name = UnitsName.TryGetValue(u, out var s) ? s : u.ToString();
            var bp = GetStoredBasePoint();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["units"] = name,
                    ["tolerances"] = new JObject
                    {
                        ["absolute"] = Doc.ModelAbsoluteTolerance,
                        ["angle_degrees"] = Doc.ModelAngleToleranceDegrees,
                        ["relative"] = Doc.ModelRelativeTolerance,
                    },
                    ["base_point"] = new JObject { ["x"] = bp.X, ["y"] = bp.Y, ["z"] = bp.Z },
                },
                ["text"] = $"{name} | abs={Doc.ModelAbsoluteTolerance} | base=({bp.X:F3},{bp.Y:F3},{bp.Z:F3})",
            };
        }
    }
}

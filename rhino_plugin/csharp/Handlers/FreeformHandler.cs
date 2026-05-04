using Newtonsoft.Json.Linq;
using Rhino;
using Rhino.DocObjects;
using Rhino.Geometry;
using Rhino.Geometry.Intersect;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Free-form / non-rectilinear architectural design — true loft, plane-aligned
    /// slicing, orthogonal ribs (waffle), full Gaussian / mean / principal curvature,
    /// and uniform paneling helpers powered by RhinoCommon.
    /// </summary>
    public class FreeformHandler : HandlerBase
    {
        // ── Skin / sections ──────────────────────────────────────────────
        public JObject Skin(JObject p)
        {
            var ids = p["section_curve_ids"]!.Select(t => t.ToString()).ToList();
            var curves = ids.Select(id => FindCurve(id) ?? throw new ArgumentException($"not a curve: {id}")).ToList();
            var closed = p["closed"]?.Value<bool>() ?? false;
            var breps = Brep.CreateFromLoft(curves, Point3d.Unset, Point3d.Unset, LoftType.Normal, closed);
            if (breps == null || breps.Length == 0)
                throw new InvalidOperationException("Loft failed");
            var attrs = new ObjectAttributes();
            var layer = p["layer"]?.ToString();
            if (!string.IsNullOrEmpty(layer))
            {
                int li = Doc.Layers.FindByFullPath(layer, -1);
                if (li < 0) li = Doc.Layers.Add(new Layer { Name = layer });
                attrs.LayerIndex = li;
            }
            var name = p["name"]?.ToString();
            if (!string.IsNullOrEmpty(name)) attrs.Name = name;
            var newIds = new JArray();
            foreach (var b in breps)
            {
                var id = Doc.Objects.AddBrep(b, attrs);
                newIds.Add(id.ToString());
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_ids"] = newIds, ["section_count"] = ids.Count, ["closed"] = closed },
                ["text"] = $"Loft built as {newIds.Count} Brep(s) from {ids.Count} sections",
            };
        }

        public JObject SectionAtAxis(JObject p)
        {
            var oid = p["object_id"]!.ToString();
            var axis = p["axis"]!.ToString().ToLowerInvariant();
            var count = p["count"]!.Value<int>();
            var layer = p["layer"]?.ToString();

            int layerIdx = -1;
            if (!string.IsNullOrEmpty(layer))
            {
                layerIdx = Doc.Layers.FindByFullPath(layer, -1);
                if (layerIdx < 0) layerIdx = Doc.Layers.Add(new Layer { Name = layer });
            }
            ObjectAttributes Attrs()
            {
                var a = new ObjectAttributes();
                if (layerIdx >= 0) a.LayerIndex = layerIdx;
                return a;
            }

            // Surface isocurves (u/v) — works for surfaces and single-face Breps.
            if (axis == "u" || axis == "v")
            {
                Surface? srf = FindGeometry(oid) switch
                {
                    Surface s => s,
                    Brep brep when brep.Faces.Count == 1 => brep.Faces[0].UnderlyingSurface(),
                    _ => null,
                };
                if (srf == null) throw new ArgumentException("axis='u'|'v' needs a surface or single-face Brep");
                int dir = axis == "v" ? 0 : 1;
                var dom = dir == 0 ? srf.Domain(0) : srf.Domain(1);
                var ids = new JArray();
                for (int k = 0; k < count; k++)
                {
                    double t = dom.T0 + (dom.T1 - dom.T0) * (k / (double)Math.Max(count - 1, 1));
                    var iso = srf.IsoCurve(dir, t);
                    if (iso == null) continue;
                    var id = Doc.Objects.AddCurve(iso, Attrs());
                    ids.Add(id.ToString());
                }
                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject { ["object_ids"] = ids, ["axis"] = axis, ["count"] = ids.Count },
                    ["text"] = $"Sectioned {ids.Count} {axis}-isocurves",
                };
            }

            // World-axis slicing — works for any Brep / Mesh.
            var geom = FindGeometry(oid) ?? throw new ArgumentException($"object not found: {oid}");
            BoundingBox bb = geom.GetBoundingBox(true);
            Vector3d normal = axis switch
            {
                "x" => Vector3d.XAxis,
                "y" => Vector3d.YAxis,
                "z" => Vector3d.ZAxis,
                _ => throw new ArgumentException($"axis must be x/y/z/u/v, got '{axis}'"),
            };
            double minT = axis == "x" ? bb.Min.X : axis == "y" ? bb.Min.Y : bb.Min.Z;
            double maxT = axis == "x" ? bb.Max.X : axis == "y" ? bb.Max.Y : bb.Max.Z;

            var outIds = new JArray();
            for (int k = 0; k < count; k++)
            {
                double t = minT + (maxT - minT) * ((k + 1) / (double)(count + 1)); // skip extremes
                var origin = axis == "x" ? new Point3d(t, 0, 0) : axis == "y" ? new Point3d(0, t, 0) : new Point3d(0, 0, t);
                var plane = new Plane(origin, normal);
                if (geom is Brep b)
                {
                    if (Intersection.BrepPlane(b, plane, Doc.ModelAbsoluteTolerance, out var crvs, out _))
                    {
                        if (crvs != null)
                            foreach (var c in crvs)
                                outIds.Add(Doc.Objects.AddCurve(c, Attrs()).ToString());
                    }
                }
                else if (geom is Mesh m)
                {
                    var poly = Intersection.MeshPlane(m, new[] { plane });
                    if (poly != null)
                        foreach (var pl in poly)
                            outIds.Add(Doc.Objects.AddPolyline(pl, Attrs()).ToString());
                }
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_ids"] = outIds, ["axis"] = axis, ["count"] = outIds.Count },
                ["text"] = $"Sectioned {outIds.Count} curves along {axis}",
            };
        }

        public JObject AxisRibs(JObject p)
        {
            var oid = p["object_id"]!.ToString();
            var axisA = p["axis_a"]!.ToString().ToLowerInvariant();
            var axisB = p["axis_b"]!.ToString().ToLowerInvariant();
            if (axisA == axisB) throw new ArgumentException("axis_a and axis_b must differ");
            var countA = p["count_a"]!.Value<int>();
            var countB = p["count_b"]!.Value<int>();
            var layer = p["layer"]?.ToString();

            // Reuse SectionAtAxis twice
            var aReq = new JObject { ["object_id"] = oid, ["axis"] = axisA, ["count"] = countA, ["layer"] = layer };
            var bReq = new JObject { ["object_id"] = oid, ["axis"] = axisB, ["count"] = countB, ["layer"] = layer };
            var aRes = SectionAtAxis(aReq);
            var bRes = SectionAtAxis(bReq);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["axis_a_ids"] = aRes["summary"]!["object_ids"],
                    ["axis_b_ids"] = bRes["summary"]!["object_ids"],
                    ["axis_a"] = axisA,
                    ["axis_b"] = axisB,
                },
                ["text"] = $"Waffle ribs: {aRes["summary"]!["count"]} along {axisA}, {bRes["summary"]!["count"]} along {axisB}",
            };
        }

        // ── Curvature ─────────────────────────────────────────────────────
        public JObject NormalAt(JObject p)
        {
            var srf = ResolveSurface(p["surface_id"]!.ToString());
            double u = NormalisedToParam(srf, p["u"]!.Value<double>(), 0);
            double v = NormalisedToParam(srf, p["v"]!.Value<double>(), 1);
            var n = srf.NormalAt(u, v);
            var pt = srf.PointAt(u, v);
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["point"] = new JObject { ["x"] = pt.X, ["y"] = pt.Y, ["z"] = pt.Z },
                    ["normal"] = new JObject { ["x"] = n.X, ["y"] = n.Y, ["z"] = n.Z },
                    ["u"] = p["u"]!.Value<double>(),
                    ["v"] = p["v"]!.Value<double>(),
                },
                ["text"] = "Surface normal evaluated",
            };
        }

        public JObject CurvatureAt(JObject p)
        {
            var srf = ResolveSurface(p["surface_id"]!.ToString());
            double u = NormalisedToParam(srf, p["u"]!.Value<double>(), 0);
            double v = NormalisedToParam(srf, p["v"]!.Value<double>(), 1);
            var c = srf.CurvatureAt(u, v);
            if (c == null) throw new InvalidOperationException("Curvature evaluation failed");
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["gaussian"] = c.Gaussian,
                    ["mean"] = c.Mean,
                    ["k1"] = c.Kappa(0),
                    ["k2"] = c.Kappa(1),
                    ["direction_1"] = new JObject { ["x"] = c.Direction(0).X, ["y"] = c.Direction(0).Y, ["z"] = c.Direction(0).Z },
                    ["direction_2"] = new JObject { ["x"] = c.Direction(1).X, ["y"] = c.Direction(1).Y, ["z"] = c.Direction(1).Z },
                    ["normal"] = new JObject { ["x"] = c.Normal.X, ["y"] = c.Normal.Y, ["z"] = c.Normal.Z },
                    ["point"] = new JObject { ["x"] = c.Point.X, ["y"] = c.Point.Y, ["z"] = c.Point.Z },
                },
                ["text"] = $"K={c.Gaussian:G3}, H={c.Mean:G3}, k1={c.Kappa(0):G3}, k2={c.Kappa(1):G3}",
            };
        }

        public JObject DevelopableScore(JObject p)
        {
            var srf = ResolveSurface(p["surface_id"]!.ToString());
            int su = p["sample_u"]!.Value<int>();
            int sv = p["sample_v"]!.Value<int>();
            var du = srf.Domain(0);
            var dv = srf.Domain(1);
            // Sample true Gaussian curvature and report its peak / mean abs.
            double maxK = 0;
            double sumAbs = 0;
            int n = 0;
            for (int j = 0; j <= sv; j++)
            {
                double v = dv.T0 + (dv.T1 - dv.T0) * (j / (double)sv);
                for (int i = 0; i <= su; i++)
                {
                    double u = du.T0 + (du.T1 - du.T0) * (i / (double)su);
                    var c = srf.CurvatureAt(u, v);
                    if (c == null) continue;
                    double k = Math.Abs(c.Gaussian);
                    if (k > maxK) maxK = k;
                    sumAbs += k;
                    n++;
                }
            }
            double mean = n > 0 ? sumAbs / n : 0;
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["max_abs_gaussian"] = maxK,
                    ["mean_abs_gaussian"] = mean,
                    ["sample_count"] = n,
                    // Standalone-compatible normalised score: 0 ≈ developable.
                    ["score_normalised"] = Math.Min(maxK * 10.0, 1.0),
                },
                ["text"] = $"Gaussian curvature max={maxK:G3}, mean={mean:G3}",
            };
        }

        // ── Paneling ──────────────────────────────────────────────────────
        public JObject UvGridPanels(JObject p)
        {
            var srf = ResolveSurface(p["surface_id"]!.ToString());
            int cu = p["count_u"]!.Value<int>();
            int cv = p["count_v"]!.Value<int>();
            var output = p["output"]?.ToString() ?? "mesh";
            var layer = p["layer"]?.ToString();
            int layerIdx = -1;
            if (!string.IsNullOrEmpty(layer))
            {
                layerIdx = Doc.Layers.FindByFullPath(layer, -1);
                if (layerIdx < 0) layerIdx = Doc.Layers.Add(new Layer { Name = layer });
            }
            var attrs = new ObjectAttributes();
            if (layerIdx >= 0) attrs.LayerIndex = layerIdx;

            var du = srf.Domain(0);
            var dv = srf.Domain(1);

            if (output == "mesh")
            {
                var m = new Mesh();
                for (int j = 0; j <= cv; j++)
                {
                    double v = dv.T0 + (dv.T1 - dv.T0) * (j / (double)cv);
                    for (int i = 0; i <= cu; i++)
                    {
                        double u = du.T0 + (du.T1 - du.T0) * (i / (double)cu);
                        m.Vertices.Add(srf.PointAt(u, v));
                    }
                }
                int stride = cu + 1;
                for (int j = 0; j < cv; j++)
                    for (int i = 0; i < cu; i++)
                        m.Faces.AddFace(i + stride * j, (i + 1) + stride * j, (i + 1) + stride * (j + 1), i + stride * (j + 1));
                m.Normals.ComputeNormals();
                m.Compact();
                var id = Doc.Objects.AddMesh(m, attrs);
                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject { ["object_id"] = id.ToString(), ["count_u"] = cu, ["count_v"] = cv, ["panel_count"] = cu * cv },
                    ["text"] = $"Panel mesh: {cu * cv} quads",
                };
            }

            if (output == "curves")
            {
                var ids = new JArray();
                for (int j = 0; j <= cv; j++)
                {
                    double v = dv.T0 + (dv.T1 - dv.T0) * (j / (double)cv);
                    var iso = srf.IsoCurve(1, v);
                    if (iso != null) ids.Add(Doc.Objects.AddCurve(iso, attrs).ToString());
                }
                for (int i = 0; i <= cu; i++)
                {
                    double u = du.T0 + (du.T1 - du.T0) * (i / (double)cu);
                    var iso = srf.IsoCurve(0, u);
                    if (iso != null) ids.Add(Doc.Objects.AddCurve(iso, attrs).ToString());
                }
                Doc.Views.Redraw();
                return new JObject
                {
                    ["summary"] = new JObject { ["object_ids"] = ids, ["count_u"] = cu, ["count_v"] = cv },
                    ["text"] = $"Wrote {ids.Count} isocurves",
                };
            }

            if (output == "corners")
            {
                var corners = new JArray();
                for (int j = 0; j <= cv; j++)
                {
                    double v = dv.T0 + (dv.T1 - dv.T0) * (j / (double)cv);
                    for (int i = 0; i <= cu; i++)
                    {
                        double u = du.T0 + (du.T1 - du.T0) * (i / (double)cu);
                        var pt = srf.PointAt(u, v);
                        corners.Add(new JObject { ["i"] = i, ["j"] = j, ["x"] = pt.X, ["y"] = pt.Y, ["z"] = pt.Z });
                    }
                }
                return new JObject
                {
                    ["summary"] = new JObject { ["corners"] = corners, ["count_u"] = cu, ["count_v"] = cv },
                    ["text"] = $"Sampled {corners.Count} corners",
                };
            }
            throw new ArgumentException("output must be 'mesh', 'curves', or 'corners'");
        }

        public JObject PanelPlanarity(JObject p)
        {
            var srf = ResolveSurface(p["surface_id"]!.ToString());
            int cu = p["count_u"]!.Value<int>();
            int cv = p["count_v"]!.Value<int>();
            double tol = p["tolerance"]?.Value<double>() ?? 0.001;
            var du = srf.Domain(0);
            var dv = srf.Domain(1);
            var grid = new Point3d[cv + 1, cu + 1];
            for (int j = 0; j <= cv; j++)
            {
                double v = dv.T0 + (dv.T1 - dv.T0) * (j / (double)cv);
                for (int i = 0; i <= cu; i++)
                {
                    double u = du.T0 + (du.T1 - du.T0) * (i / (double)cu);
                    grid[j, i] = srf.PointAt(u, v);
                }
            }
            var cells = new JArray();
            double maxErr = 0, sumErr = 0;
            int violators = 0;
            for (int j = 0; j < cv; j++)
            {
                for (int i = 0; i < cu; i++)
                {
                    var p00 = grid[j, i];
                    var p10 = grid[j, i + 1];
                    var p01 = grid[j + 1, i];
                    var p11 = grid[j + 1, i + 1];
                    var n = Vector3d.CrossProduct(p10 - p00, p01 - p00);
                    double err;
                    if (n.Length > 0)
                    {
                        n.Unitize();
                        err = Math.Abs((p11 - p00) * n);
                    }
                    else err = 0;
                    cells.Add(new JObject { ["i"] = i, ["j"] = j, ["planarity_error"] = err, ["violates"] = err > tol });
                    if (err > maxErr) maxErr = err;
                    sumErr += err;
                    if (err > tol) violators++;
                }
            }
            int total = cu * cv;
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["count_u"] = cu,
                    ["count_v"] = cv,
                    ["panel_count"] = total,
                    ["tolerance"] = tol,
                    ["stats"] = new JObject
                    {
                        ["max_error"] = maxErr,
                        ["mean_error"] = total > 0 ? sumErr / total : 0,
                        ["non_planar_count"] = violators,
                        ["planar_ratio"] = total > 0 ? (total - violators) / (double)total : 1.0,
                    },
                    ["panels"] = cells,
                },
                ["text"] = $"Panel planarity: {violators}/{total} non-planar, max={maxErr:G6}",
            };
        }

        public JObject PanelCurvatureClassify(JObject p)
        {
            var srf = ResolveSurface(p["surface_id"]!.ToString());
            int cu = p["count_u"]!.Value<int>();
            int cv = p["count_v"]!.Value<int>();
            double planarTol = p["planar_tolerance"]?.Value<double>() ?? 0.001;

            var du = srf.Domain(0);
            var dv = srf.Domain(1);
            int total = cu * cv;
            int planar = 0, single_u = 0, single_v = 0, sync = 0, anti = 0;
            var cells = new JArray();
            // Use true Gaussian sign per cell (sample at centre).
            for (int j = 0; j < cv; j++)
            {
                double v = dv.T0 + (dv.T1 - dv.T0) * ((j + 0.5) / cv);
                for (int i = 0; i < cu; i++)
                {
                    double u = du.T0 + (du.T1 - du.T0) * ((i + 0.5) / cu);
                    var c = srf.CurvatureAt(u, v);
                    string klass;
                    double K = c?.Gaussian ?? 0;
                    double H = c?.Mean ?? 0;
                    double K_abs = Math.Abs(K);
                    double H_abs = Math.Abs(H);
                    if (K_abs < planarTol && H_abs < planarTol) { klass = "planar"; planar++; }
                    else if (K_abs < planarTol)
                    {
                        // Single-curved: use principal direction to decide u/v
                        if (c == null) { klass = "single_curved_u"; single_u++; }
                        else
                        {
                            // Compare direction(0) projection onto surface u-tangent vs v-tangent.
                            var k1dir = c.Direction(0);
                            // Approximate u-tangent direction
                            srf.Evaluate(u, v, 1, out _, out var derivs);
                            if (derivs != null && derivs.Length >= 2)
                            {
                                var du_t = derivs[0]; du_t.Unitize();
                                var dv_t = derivs[1]; dv_t.Unitize();
                                if (Math.Abs(k1dir * du_t) > Math.Abs(k1dir * dv_t)) { klass = "single_curved_u"; single_u++; }
                                else { klass = "single_curved_v"; single_v++; }
                            }
                            else { klass = "single_curved_u"; single_u++; }
                        }
                    }
                    else if (K > 0) { klass = "synclastic"; sync++; }
                    else { klass = "anticlastic"; anti++; }
                    cells.Add(new JObject { ["i"] = i, ["j"] = j, ["class"] = klass, ["gaussian"] = K, ["mean"] = H });
                }
            }
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["count_u"] = cu,
                    ["count_v"] = cv,
                    ["panel_count"] = total,
                    ["class_counts"] = new JObject
                    {
                        ["planar"] = planar,
                        ["single_curved_u"] = single_u,
                        ["single_curved_v"] = single_v,
                        ["synclastic"] = sync,
                        ["anticlastic"] = anti,
                    },
                    ["panels"] = cells,
                },
                ["text"] = $"planar={planar}, single_u={single_u}, single_v={single_v}, sync={sync}, anti={anti}",
            };
        }

        // ── Fields ────────────────────────────────────────────────────────
        public JObject AttractorDisplacePoints(JObject p)
        {
            var ids = p["point_object_ids"]!.Select(t => t.ToString()).ToList();
            Point3d? attractor = p["attractor_point"] != null && p["attractor_point"]!.Type != JTokenType.Null
                ? ToPoint(p["attractor_point"]!) : null;
            string? attractorCurveId = p["attractor_curve_id"]?.ToString();
            if ((attractor.HasValue) == !string.IsNullOrEmpty(attractorCurveId))
                throw new ArgumentException("provide exactly one of attractor_point or attractor_curve_id");
            Curve? attCrv = string.IsNullOrEmpty(attractorCurveId) ? null : FindCurve(attractorCurveId);
            string falloff = p["falloff"]?.ToString() ?? "linear";
            double strength = p["strength"]?.Value<double>() ?? 1.0;
            double maxD = p["max_distance"]?.Value<double>() ?? 50.0;

            double Weight(double d)
            {
                if (d >= maxD && falloff != "gaussian") return 0;
                return falloff switch
                {
                    "linear" => 1.0 - d / maxD,
                    "inverse" => 1.0 / (1.0 + d),
                    "gaussian" => Math.Exp(-(d * d) / (maxD * maxD)),
                    _ => throw new ArgumentException($"unknown falloff '{falloff}'"),
                };
            }

            var newIds = new JArray();
            var skipped = new JArray();
            foreach (var id in ids)
            {
                var obj = FindObject(id);
                if (obj == null || obj.Geometry is not Rhino.Geometry.Point pt)
                {
                    skipped.Add(id);
                    continue;
                }
                Point3d p0 = pt.Location;
                Point3d target;
                double dist;
                if (attractor.HasValue)
                {
                    target = attractor.Value;
                    dist = p0.DistanceTo(target);
                }
                else
                {
                    attCrv!.ClosestPoint(p0, out double t);
                    target = attCrv.PointAt(t);
                    dist = p0.DistanceTo(target);
                }
                double w = Weight(dist);
                if (w == 0) continue;
                var disp = (target - p0) * (strength * w);
                var newPt = new Rhino.Geometry.Point(p0 + disp);
                var attrs = obj.Attributes.Duplicate();
                Doc.Objects.Delete(obj.Id, true);
                var nid = Doc.Objects.AddPoint(newPt.Location, attrs);
                newIds.Add(nid.ToString());
            }
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["object_ids"] = newIds,
                    ["skipped"] = skipped,
                    ["input_count"] = ids.Count,
                    ["moved"] = newIds.Count,
                },
                ["text"] = $"Attractor: moved {newIds.Count}/{ids.Count}",
            };
        }

        public JObject SmoothPolyline(JObject p)
        {
            var oid = p["curve_id"]!.ToString();
            var crv = FindCurve(oid) ?? throw new ArgumentException($"not a curve: {oid}");
            int iters = p["iterations"]!.Value<int>();
            double f = p["factor"]!.Value<double>();
            bool pin = p["pin_endpoints"]?.Value<bool>() ?? true;

            // Pull control points.
            var nc = crv.ToNurbsCurve();
            var pts = nc.Points.Select(cp => new Point3d(cp.Location.X, cp.Location.Y, cp.Location.Z)).ToList();
            int n = pts.Count;
            if (n < 3)
                return new JObject
                {
                    ["summary"] = new JObject { ["object_id"] = oid, ["iterations"] = 0 },
                    ["text"] = "fewer than 3 points; nothing to smooth",
                };
            for (int it = 0; it < iters; it++)
            {
                var newPts = new List<Point3d>(pts);
                for (int i = 1; i < n - 1; i++)
                {
                    var avg = new Point3d(
                        0.5 * (pts[i - 1].X + pts[i + 1].X),
                        0.5 * (pts[i - 1].Y + pts[i + 1].Y),
                        0.5 * (pts[i - 1].Z + pts[i + 1].Z));
                    newPts[i] = new Point3d(
                        (1 - f) * pts[i].X + f * avg.X,
                        (1 - f) * pts[i].Y + f * avg.Y,
                        (1 - f) * pts[i].Z + f * avg.Z);
                }
                if (!pin && n >= 2)
                {
                    newPts[0] = new Point3d(
                        (1 - f) * pts[0].X + f * pts[1].X,
                        (1 - f) * pts[0].Y + f * pts[1].Y,
                        (1 - f) * pts[0].Z + f * pts[1].Z);
                    newPts[n - 1] = new Point3d(
                        (1 - f) * pts[n - 1].X + f * pts[n - 2].X,
                        (1 - f) * pts[n - 1].Y + f * pts[n - 2].Y,
                        (1 - f) * pts[n - 1].Z + f * pts[n - 2].Z);
                }
                pts = newPts;
            }
            Curve newCurve = NurbsCurve.Create(false, nc.Degree, pts);
            if (newCurve == null) newCurve = new PolylineCurve(pts);
            var oldObj = FindObject(oid)!;
            var attrs = oldObj.Attributes.Duplicate();
            Doc.Objects.Delete(oldObj.Id, true);
            var newId = Doc.Objects.AddCurve(newCurve, attrs);
            Doc.Views.Redraw();
            return new JObject
            {
                ["summary"] = new JObject { ["object_id"] = newId.ToString(), ["iterations"] = iters, ["factor"] = f },
                ["text"] = $"Smoothed: {iters} iters, f={f}",
            };
        }

        // ── Helpers ───────────────────────────────────────────────────────
        private static Surface ResolveSurface(string id)
        {
            var g = FindGeometry(id);
            return g switch
            {
                Surface s => s,
                Brep b when b.Faces.Count == 1 => b.Faces[0].UnderlyingSurface(),
                _ => throw new ArgumentException($"surface_id must reference a Surface or single-face Brep: {id}"),
            };
        }

        private static double NormalisedToParam(Surface srf, double t01, int axis)
        {
            var d = srf.Domain(axis);
            return d.T0 + (d.T1 - d.T0) * t01;
        }
    }
}

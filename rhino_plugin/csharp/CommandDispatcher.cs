using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMCPBridge
{
    /// <summary>
    /// Routes JSON-RPC method names to handler classes.
    /// Method names follow the pattern <c>namespace.category.action</c>.
    /// </summary>
    public class CommandDispatcher
    {
        private readonly Dictionary<string, Func<JObject, JObject>> _handlers = new();

        public CommandDispatcher()
        {
            // Core
            Register("rhino.ping", _ => Ping());

            // Geometry (points, curves, primitives)
            var geo = new Handlers.GeometryHandler();
            Register("rhino.geometry.point", geo.Point);
            Register("rhino.geometry.line", geo.Line);
            Register("rhino.geometry.polyline", geo.Polyline);
            Register("rhino.geometry.arc", geo.Arc);
            Register("rhino.geometry.circle", geo.Circle);
            Register("rhino.geometry.ellipse", geo.Ellipse);
            Register("rhino.geometry.rectangle", geo.Rectangle);
            Register("rhino.geometry.polygon", geo.Polygon);
            Register("rhino.geometry.nurbs_curve", geo.NurbsCurve);
            Register("rhino.geometry.helix", geo.Helix);
            Register("rhino.geometry.spiral", geo.Spiral);

            // Curves
            var crv = new Handlers.CurveHandler();
            Register("rhino.curve.length", crv.Length);
            Register("rhino.curve.point_at", crv.PointAt);
            Register("rhino.curve.split", crv.Split);

            // Solids
            var sol = new Handlers.SolidHandler();
            Register("rhino.solid.box", sol.Box);
            Register("rhino.solid.sphere", sol.Sphere);
            Register("rhino.solid.cylinder", sol.Cylinder);
            Register("rhino.solid.cone", sol.Cone);
            Register("rhino.solid.torus", sol.Torus);
            Register("rhino.solid.boolean_union", sol.BooleanUnion);
            Register("rhino.solid.boolean_difference", sol.BooleanDifference);
            Register("rhino.solid.boolean_intersection", sol.BooleanIntersection);
            Register("rhino.solid.cap_holes", sol.CapHoles);
            Register("rhino.solid.shell", sol.Shell);

            // Surfaces
            var srf = new Handlers.SurfaceHandler();
            Register("rhino.surface.plane_surface", srf.PlaneSurface);
            Register("rhino.surface.extrude", srf.Extrude);
            Register("rhino.surface.revolve", srf.Revolve);
            Register("rhino.surface.loft", srf.Loft);
            Register("rhino.surface.sweep1", srf.Sweep1);
            Register("rhino.surface.sweep2", srf.Sweep2);
            Register("rhino.surface.network", srf.NetworkSurface);
            Register("rhino.surface.patch", srf.Patch);
            Register("rhino.surface.blend", srf.BlendSurface);
            Register("rhino.surface.fillet", srf.FilletSurface);
            Register("rhino.surface.offset", srf.OffsetSurface);

            // Mesh
            var mesh = new Handlers.MeshHandler();
            Register("rhino.mesh.box", mesh.Box);
            Register("rhino.mesh.from_brep", mesh.FromBrep);
            Register("rhino.mesh.from_surface", mesh.FromSurface);
            Register("rhino.mesh.boolean_union", mesh.BooleanUnion);
            Register("rhino.mesh.boolean_difference", mesh.BooleanDifference);
            Register("rhino.mesh.weld", mesh.Weld);
            Register("rhino.mesh.unweld", mesh.Unweld);
            Register("rhino.mesh.reduce", mesh.Reduce);

            // Transform
            var xf = new Handlers.TransformHandler();
            Register("rhino.transform.move", xf.Move);
            Register("rhino.transform.rotate", xf.Rotate);
            Register("rhino.transform.scale", xf.Scale);
            Register("rhino.transform.mirror", xf.Mirror);
            Register("rhino.transform.orient", xf.Orient);
            Register("rhino.transform.array_linear", xf.ArrayLinear);
            Register("rhino.transform.array_polar", xf.ArrayPolar);
            Register("rhino.transform.flow", xf.Flow);
            Register("rhino.transform.cage_edit", xf.CageEdit);
            Register("rhino.transform.selection_bbox", xf.SelectionBbox);

            // Layers
            var lay = new Handlers.LayerHandler();
            Register("rhino.layer.create", lay.Create);
            Register("rhino.layer.delete", lay.Delete);
            Register("rhino.layer.set_color", lay.SetColor);

            // Materials
            var mat = new Handlers.MaterialHandler();
            Register("rhino.material.create", mat.Create);
            Register("rhino.material.assign", mat.Assign);

            // Annotation
            var ann = new Handlers.AnnotationHandler();
            Register("rhino.annotation.text", ann.Text);
            Register("rhino.annotation.text_dot", ann.TextDot);
            Register("rhino.annotation.dim_linear", ann.DimLinear);
            Register("rhino.annotation.dim_aligned", ann.DimAligned);
            Register("rhino.annotation.dim_angular", ann.DimAngular);
            Register("rhino.annotation.leader", ann.Leader);
            Register("rhino.annotation.hatch", ann.Hatch);
            Register("rhino.annotation.clipping_plane", ann.ClippingPlane);

            // Display
            var dsp = new Handlers.DisplayHandler();
            Register("rhino.display.view_set", dsp.ViewSet);
            Register("rhino.display.zoom_extent", dsp.ZoomExtent);
            Register("rhino.display.named_view_save", dsp.NamedViewSave);
            Register("rhino.display.mode_set", dsp.ModeSet);
            Register("rhino.display.turntable", dsp.Turntable);
            Register("rhino.render.viewport", dsp.RenderViewport);

            // Analysis
            var anl = new Handlers.AnalysisHandler();
            Register("rhino.analysis.bounding_box", anl.BoundingBox);
            Register("rhino.analysis.volume", anl.Volume);
            Register("rhino.analysis.area", anl.Area);
            Register("rhino.analysis.distance", anl.Distance);
            Register("rhino.analysis.curvature", anl.Curvature);
            Register("rhino.analysis.draft_angle", anl.DraftAngle);
            Register("rhino.analysis.section", anl.Section);
            Register("rhino.analysis.contour", anl.Contour);
            Register("rhino.analysis.zebra", anl.Zebra);

            // IO
            var io = new Handlers.IOHandler();
            Register("rhino.io.open", io.Open);
            Register("rhino.io.save", io.Save);
            Register("rhino.io.import", io.Import);
            Register("rhino.io.export_step", io.ExportStep);
            Register("rhino.io.export_iges", io.ExportIges);
            Register("rhino.io.export_obj", io.ExportObj);
            Register("rhino.io.export_stl", io.ExportStl);
            Register("rhino.io.export_dxf", io.ExportDxf);
            Register("rhino.io.screenshot", io.Screenshot);

            // Object operations
            var obj = new Handlers.ObjectHandler();
            Register("rhino.object.delete", obj.Delete);
            Register("rhino.object.select", obj.Select);
            Register("rhino.object.move_to_layer", obj.MoveToLayer);
            Register("rhino.block.create", obj.BlockCreate);
            Register("rhino.block.insert", obj.BlockInsert);
            Register("rhino.group.create", obj.GroupCreate);

            // Query (read-only document inspection)
            var qry = new Handlers.QueryHandler();
            Register("rhino.query.list_objects", qry.ListObjects);
            Register("rhino.query.object_info", qry.ObjectInfo);
            Register("rhino.query.document_summary", qry.DocumentSummary);
            Register("rhino.query.layer_list", qry.LayerList);
            Register("rhino.query.get_user_text", qry.GetUserText);
            Register("rhino.query.set_user_text", qry.SetUserText);

            // Script execution
            var scr = new Handlers.ScriptHandler();
            Register("rhino.script.execute_python", scr.ExecutePython);
            Register("rhino.script.execute_csharp", scr.ExecuteCSharp);

            // History (undo/redo)
            var hist = new Handlers.HistoryHandler();
            Register("rhino.history.undo", hist.Undo);
            Register("rhino.history.redo", hist.Redo);

            // Batch operations
            var bat = new Handlers.BatchHandler();
            Register("rhino.batch.modify", bat.Modify);

            // Selected objects query
            Register("rhino.query.selected_objects", qry.SelectedObjects);

            // Deformation
            var def = new Handlers.DeformationHandler();
            Register("rhino.deform.bend", def.Bend);
            Register("rhino.deform.twist", def.Twist);
            Register("rhino.deform.taper", def.Taper);
            Register("rhino.deform.flow_along_curve", def.FlowAlongCurve);

            // NURBS
            var nrb = new Handlers.NurbsHandler();
            Register("rhino.geometry.rebuild_curve", nrb.RebuildCurve);
            Register("rhino.nurbs.rebuild_surface", nrb.RebuildSurface);
            Register("rhino.nurbs.surface_from_points", nrb.SurfaceFromPoints);
            Register("rhino.nurbs.unroll", nrb.Unroll);
            Register("rhino.nurbs.closest_point", nrb.ClosestPoint);
            Register("rhino.nurbs.evaluate", nrb.Evaluate);

            // SubD
            var sub = new Handlers.SubDHandler();
            Register("rhino.subd.create", sub.Create);
            Register("rhino.subd.to_nurbs", sub.ToNurbs);

            // Surface matching
            var smatch = new Handlers.SurfaceMatchHandler();
            Register("rhino.surface_match.match", smatch.Match);
            Register("rhino.surface_match.blend", smatch.Blend);
            Register("rhino.surface_match.merge", smatch.Merge);

            // Extraction
            var ext = new Handlers.ExtractionHandler();
            Register("rhino.extract.dup_edge", ext.DupEdge);
            Register("rhino.extract.dup_border", ext.DupBorder);
            Register("rhino.extract.isocurve", ext.Isocurve);
            Register("rhino.extract.make2d", ext.Make2D);

            // Control points
            var cp = new Handlers.ControlPointHandler();
            Register("rhino.cp.get", cp.Get);
            Register("rhino.cp.set", cp.Set);

            // Paneling
            var pnl = new Handlers.PanelingHandler();
            Register("rhino.panel.panelize", pnl.Panelize);
            Register("rhino.panel.uv_grid", pnl.UvGrid);
            Register("rhino.panel.frames", pnl.Frames);

            // Grasshopper
            var gh = new Handlers.GrasshopperHandler();
            Register("gh.canvas.open", gh.CanvasOpen);
            Register("gh.canvas.save", gh.CanvasSave);
            Register("gh.canvas.new", gh.CanvasNew);
            Register("gh.canvas.run", gh.CanvasRun);
            Register("gh.canvas.reset", gh.CanvasReset);
            Register("gh.canvas.preview_toggle", gh.CanvasPreviewToggle);
            Register("gh.canvas.bake", gh.CanvasBake);
            Register("gh.component.add", gh.ComponentAdd);
            Register("gh.component.delete", gh.ComponentDelete);
            Register("gh.component.connect", gh.ComponentConnect);
            Register("gh.component.list", gh.ComponentList);
            Register("gh.cluster.create", gh.ClusterCreate);
            Register("gh.cluster.expand", gh.ClusterExpand);
            Register("gh.parameter.get", gh.ParameterGet);
            Register("gh.parameter.set", gh.ParameterSet);
            Register("gh.parameter.set_slider", gh.ParameterSetSlider);
            Register("gh.parameter.set_toggle", gh.ParameterSetToggle);
            Register("gh.parameter.set_panel", gh.ParameterSetPanel);
            Register("gh.data_tree.get", gh.DataTreeGet);
            Register("gh.data_tree.set", gh.DataTreeSet);
        }

        private void Register(string method, Func<JObject, JObject> handler)
        {
            _handlers[method] = handler;
        }

        public JObject Dispatch(string method, JObject parameters)
        {
            if (!_handlers.TryGetValue(method, out var handler))
                throw new KeyNotFoundException($"Unknown method: {method}");

            return handler(parameters);
        }

        private static JObject Ping()
        {
            var rhinoVersion = RhinoApp.Version.ToString();
            string? ghVersion = null;
            try
            {
                ghVersion = Grasshopper.Versioning.Version.ToString();
            }
            catch { /* Grasshopper may not be loaded */ }

            return new JObject
            {
                ["rhino"] = rhinoVersion,
                ["grasshopper"] = ghVersion,
                ["bridge_version"] = "0.1.0",
                ["bridge_type"] = "csharp"
            };
        }
    }
}

"""Schedule / quantity-takeoff workflow example.

Builds a tiny BIM-style model on disciplined layers, attaches user_text,
and runs a per-layer + per-user_text schedule. Writes a CSV next to the
model file.
"""

from rhino_mcp.document import registry
from rhino_mcp.tools.context import set_runtime
from rhino_mcp.utils.registry import Mode

set_runtime(Mode.STANDALONE, None)


def _mesh_box(min_pt, max_pt):
    """Build a closed quad mesh box from a min/max bounding box."""
    import rhino3dm as r3

    m = r3.Mesh()
    a, b, c, d = (min_pt.X, min_pt.Y, min_pt.Z), (max_pt.X, min_pt.Y, min_pt.Z), (
        max_pt.X,
        max_pt.Y,
        min_pt.Z,
    ), (min_pt.X, max_pt.Y, min_pt.Z)
    e, f, g, h = (min_pt.X, min_pt.Y, max_pt.Z), (max_pt.X, min_pt.Y, max_pt.Z), (
        max_pt.X,
        max_pt.Y,
        max_pt.Z,
    ), (min_pt.X, max_pt.Y, max_pt.Z)
    for x, y, z in (a, b, c, d, e, f, g, h):
        m.Vertices.Add(x, y, z)
    # Faces (CCW):
    m.Faces.AddFace(0, 1, 2, 3)  # bottom (-Z)
    m.Faces.AddFace(7, 6, 5, 4)  # top (+Z) reversed for outward normal
    m.Faces.AddFace(0, 4, 5, 1)
    m.Faces.AddFace(1, 5, 6, 2)
    m.Faces.AddFace(2, 6, 7, 3)
    m.Faces.AddFace(3, 7, 4, 0)
    return m


def main() -> None:
    handle = registry().get_or_create("schedule_demo")
    file3dm = handle.file3dm

    import rhino3dm as r3

    # Create disciplined layers.
    layer_specs = [
        ("Arch::Walls", (160, 160, 160, 255)),
        ("Arch::Floors", (200, 180, 140, 255)),
        ("Struct::Columns", (90, 90, 130, 255)),
    ]
    layer_indices: dict[str, int] = {}
    for name, color in layer_specs:
        layer = r3.Layer()
        layer.Name = name
        layer.Color = color
        layer_indices[name] = file3dm.Layers.Add(layer)

    # Walls — 6 mesh boxes 4x0.2x3.
    for i in range(6):
        bbox = r3.BoundingBox(r3.Point3d(i * 5, 0, 0), r3.Point3d(i * 5 + 4, 0.2, 3))
        m = _mesh_box(bbox.Min, bbox.Max)
        attrs = r3.ObjectAttributes()
        attrs.LayerIndex = layer_indices["Arch::Walls"]
        attrs.Name = f"Wall_W01_{i:02d}"
        attrs.SetUserString("function", "wall")
        attrs.SetUserString("assembly_type", "W01")
        attrs.SetUserString("material", "CIP_concrete")
        file3dm.Objects.AddMesh(m, attrs)

    # Floors — 2 mesh slabs 30x6x0.3.
    for i in range(2):
        bbox = r3.BoundingBox(r3.Point3d(0, 0, i * 3), r3.Point3d(30, 6, i * 3 + 0.3))
        m = _mesh_box(bbox.Min, bbox.Max)
        attrs = r3.ObjectAttributes()
        attrs.LayerIndex = layer_indices["Arch::Floors"]
        attrs.Name = f"Floor_F01_L{i}"
        attrs.SetUserString("function", "floor")
        attrs.SetUserString("assembly_type", "F01")
        file3dm.Objects.AddMesh(m, attrs)

    # Columns — 4 mesh prisms.
    for i in range(4):
        bbox = r3.BoundingBox(r3.Point3d(i * 7, 0, 0), r3.Point3d(i * 7 + 0.4, 0.4, 6))
        m = _mesh_box(bbox.Min, bbox.Max)
        attrs = r3.ObjectAttributes()
        attrs.LayerIndex = layer_indices["Struct::Columns"]
        attrs.Name = f"Column_C01_{i}"
        attrs.SetUserString("function", "column")
        attrs.SetUserString("assembly_type", "C01")
        file3dm.Objects.AddMesh(m, attrs)

    output = "/tmp/schedule_demo.3dm"
    file3dm.Write(output, version=8)

    # Run schedule tools through the same Bag pattern as drawing_set.py.
    from rhino_mcp.tools.schedule import (
        _ByLayerIn,
        _ByUserTextIn,
        _ExportCsvIn,
        register,
    )

    class _Bag:
        funcs: dict[str, object] = {}

        def tool(self, **_):
            def deco(fn):
                self.funcs[fn.__name__] = fn
                return fn

            return deco

    bag = _Bag()
    register(bag, Mode.STANDALONE)

    by_layer = bag.funcs["rhino_schedule_by_layer"](
        _ByLayerIn(doc_id="schedule_demo", fields=["count", "area", "volume"])
    )
    print("By layer:")
    for row in by_layer["summary"]["rows"]:
        print(f"  {row}")

    by_assembly = bag.funcs["rhino_schedule_by_user_text"](
        _ByUserTextIn(doc_id="schedule_demo", group_key="assembly_type", fields=["count", "volume"])
    )
    print("\nBy assembly_type:")
    for row in by_assembly["summary"]["rows"]:
        print(f"  {row}")

    csv_path = "/tmp/schedule_demo.csv"
    bag.funcs["rhino_schedule_export_csv"](
        _ExportCsvIn(rows=by_layer["summary"]["rows"], path=csv_path)
    )
    print(f"\nCSV written: {csv_path}")
    print(f"3DM written: {output}")


if __name__ == "__main__":
    main()

"""Drawing-set workflow example (sheet + title block + sheet metadata).

Builds a small site model, then assembles an A3 sheet with a title block,
north arrow, and scale bar. View placement / section cut / PDF export are
bridge-only; this example skips them so it stays runnable in standalone.
"""

from rhino_mcp.document import registry
from rhino_mcp.tools.context import set_runtime
from rhino_mcp.utils.registry import Mode

set_runtime(Mode.STANDALONE, None)


def main() -> None:
    from rhino_mcp.tools.annotation import register as ann_register  # noqa: F401
    from rhino_mcp.tools.drawing import register as draw_register  # noqa: F401

    handle = registry().get_or_create("drawing_demo")
    file3dm = handle.file3dm

    import rhino3dm as r3

    # Place a couple of "buildings" on a site.
    for ix, x in enumerate((0, 25, 60)):
        bbox = r3.BoundingBox(
            r3.Point3d(x, 0, 0),
            r3.Point3d(x + 12, 18, 8 + ix * 4),
        )
        attrs = r3.ObjectAttributes()
        attrs.Name = f"Block_{ix}"
        attrs.SetUserString("function", "mass")
        file3dm.Objects.AddBrep(r3.Brep.CreateFromBox(r3.Box(bbox)), attrs)

    # Use the rhino_drawing_* tools through their Pydantic models directly.
    from rhino_mcp.tools.drawing import (
        _SheetCreateIn,
        _TitleBlockIn,
    )
    from rhino_mcp.tools.drawing import register

    # Inline the FastMCP wrapper: each tool is a closure over `mcp`, so we
    # construct a temporary registry to obtain the bound functions.
    class _Bag:
        funcs: dict[str, object] = {}

        def tool(self, **_):
            def deco(fn):
                self.funcs[fn.__name__] = fn
                return fn
            return deco

    bag = _Bag()
    register(bag, Mode.STANDALONE)

    sheet = bag.funcs["rhino_drawing_sheet_create"](
        _SheetCreateIn(doc_id="drawing_demo", name="A-101", width_mm=420, height_mm=297, scale_denominator=200)
    )
    sid = sheet["summary"]["sheet_id"]

    bag.funcs["rhino_drawing_title_block_add"](
        _TitleBlockIn(
            doc_id="drawing_demo",
            sheet_id=sid,
            project="Demo Site",
            title="Massing Plan",
            scale_text="1:200",
            date_iso="2026-05-03",
            drawn_by="rhino-mcp",
            sheet_no="A-101",
            north_arrow_angle_deg=15.0,
        )
    )

    output = "/tmp/drawing_set_demo.3dm"
    file3dm.Write(output, version=8)
    print(f"Sheet ready: {output}")
    print(f"Sheet object id: {sid}")
    print(
        "Run this in bridge mode (live Rhino) to add view_place / section_cut "
        "and rhino_drawing_export_pdf."
    )


if __name__ == "__main__":
    main()

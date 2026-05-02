"""Batch geometry creation example.

Creates many 3-D objects programmatically and organises them by layer.
Runs in standalone mode.
"""

import math

from rhino_mcp.document import registry
from rhino_mcp.tools.context import set_runtime
from rhino_mcp.utils.registry import Mode

set_runtime(Mode.STANDALONE, None)


def main() -> None:
    handle = registry().get_or_create("batch_demo")
    file3dm = handle.file3dm

    import rhino3dm as r3

    # Create layers.
    for name, color in [("Spheres", (255, 0, 0, 255)), ("Boxes", (0, 0, 255, 255))]:
        layer = r3.Layer()
        layer.Name = name
        layer.Color = color
        file3dm.Layers.Add(layer)

    # 5x5 grid of spheres.
    for i in range(5):
        for j in range(5):
            center = r3.Point3d(i * 20, j * 20, 0)
            sphere = r3.Sphere(center, 3.0 + math.sin(i + j))
            brep = sphere.ToBrep()
            attrs = r3.ObjectAttributes()
            attrs.LayerIndex = 0
            attrs.Name = f"sphere_{i}_{j}"
            file3dm.Objects.AddBrep(brep, attrs)

    # 5x5 grid of boxes (offset along X).
    for i in range(5):
        for j in range(5):
            bbox = r3.BoundingBox(
                r3.Point3d(i * 20 + 100, j * 20, 0),
                r3.Point3d(i * 20 + 105 + i, j * 20 + 5 + j, 5),
            )
            box = r3.Box(bbox)
            brep = box.ToBrep()
            attrs = r3.ObjectAttributes()
            attrs.LayerIndex = 1
            attrs.Name = f"box_{i}_{j}"
            file3dm.Objects.AddBrep(brep, attrs)

    output = "/tmp/batch_geometry.3dm"
    file3dm.Write(output, version=8)
    print(f"Saved {file3dm.Objects.Count} objects to {output}")


if __name__ == "__main__":
    main()

"""배치 지오메트리 생성 예제.

여러 개의 3D 객체를 프로그래밍 방식으로 생성하고 레이어별로 정리한다.
Standalone 모드에서 실행 가능.
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

    # 레이어 생성
    for name, color in [("Spheres", (255, 0, 0, 255)), ("Boxes", (0, 0, 255, 255))]:
        layer = r3.Layer()
        layer.Name = name
        layer.Color = color
        file3dm.Layers.Add(layer)

    # 구체 5x5 그리드
    for i in range(5):
        for j in range(5):
            center = r3.Point3d(i * 20, j * 20, 0)
            sphere = r3.Sphere(center, 3.0 + math.sin(i + j))
            brep = sphere.ToBrep()
            attrs = r3.ObjectAttributes()
            attrs.LayerIndex = 0
            attrs.Name = f"sphere_{i}_{j}"
            file3dm.Objects.AddBrep(brep, attrs)

    # 박스 5x5 그리드 (오프셋)
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

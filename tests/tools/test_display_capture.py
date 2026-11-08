"""Viewport capture tools return MCP image content, not base64 text."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import pytest
from mcp.types import ImageContent, TextContent

from rhino_mcp.tools import context as tool_context
from rhino_mcp.utils.registry import Mode

_JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
_PNG = b"\x89PNG\r\n\x1a\nfake-png-bytes"


class FakeCaptureBridge:
    """Mimics the C# capture handlers: base64 payload only when ``as_base64`` is set."""

    def __init__(self, behaviour: str = "ok") -> None:
        # "ok" | "encode_error" (C# encoder failed) | "legacy" (v0.6 plug-in, path only)
        self.behaviour = behaviour
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def is_alive(self) -> bool:
        return True

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        summary: dict[str, Any] = {"path": params.get("path") or params.get("output_path")}
        response: dict[str, Any] = {"status": "ok", "summary": summary, "text": "captured"}
        if self.behaviour == "encode_error":
            response["base64_error"] = "GDI+ JPEG encoder unavailable"
        elif self.behaviour == "legacy":
            summary["output_path"] = "/tmp/rhino-mcp-capture-legacy.png"
        elif params.get("as_base64"):
            png = params.get("format") == "png"
            data = _PNG if png else _JPEG
            mime = "image/png" if png else "image/jpeg"
            response["image_base64"] = base64.b64encode(data).decode()
            response["mime"] = mime
            summary.update({"mime": mime, "image_width": params.get("max_width"), "bytes": len(data)})
        return response


def _server(behaviour: str = "ok") -> tuple[Any, FakeCaptureBridge]:
    client = FakeCaptureBridge(behaviour)
    tool_context.set_runtime(Mode.BRIDGE, client)  # type: ignore[arg-type]
    from rhino_mcp.server import build_server

    mcp, _ = build_server(runtime_mode=Mode.BRIDGE, bridge_client=client)  # type: ignore[arg-type]
    return mcp, client


@pytest.fixture
def bridge_server():
    return _server()


def _call(mcp, name: str, payload: dict[str, Any]) -> list[Any]:
    result = asyncio.run(mcp.call_tool(name, {"args": payload}))
    # Tools without an output schema return the bare content sequence.
    return list(result[0] if isinstance(result, tuple) else result)


def _split(blocks: list[Any]) -> tuple[list[ImageContent], dict[str, Any]]:
    images = [b for b in blocks if isinstance(b, ImageContent)]
    texts = [b for b in blocks if isinstance(b, TextContent)]
    assert len(texts) == 1, blocks
    assert "image_base64" not in texts[0].text
    return images, json.loads(texts[0].text)


def test_viewport_image_returns_jpeg_image_content(bridge_server) -> None:
    mcp, client = bridge_server
    images, payload = _split(_call(mcp, "rhino_viewport_image", {}))
    assert len(images) == 1
    assert images[0].mimeType == "image/jpeg"
    assert base64.b64decode(images[0].data) == _JPEG
    method, params = client.calls[-1]
    assert method == "rhino.display.capture_viewport"
    assert params["max_width"] == 1024
    assert params["format"] == "jpeg"
    assert params["jpeg_quality"] == 80
    assert params["as_base64"] is True
    assert "include_image" not in params
    assert payload["summary"]["mime"] == "image/jpeg"
    assert payload["summary"]["bytes"] == len(_JPEG)


def test_viewport_image_png_and_native_width(bridge_server) -> None:
    mcp, client = bridge_server
    images, _ = _split(_call(mcp, "rhino_viewport_image", {"format": "png", "max_width": 0}))
    assert images[0].mimeType == "image/png"
    assert client.calls[-1][1]["max_width"] == 0


def test_viewport_image_summary_only_when_image_disabled(bridge_server, tmp_path) -> None:
    mcp, client = bridge_server
    out = str(tmp_path / "v.png")
    images, payload = _split(
        _call(mcp, "rhino_viewport_image", {"include_image": False, "output_path": out})
    )
    assert images == []
    assert client.calls[-1][1]["as_base64"] is False
    assert payload["summary"]["path"] == out


def test_capture_tools_are_not_read_only_and_list_cleanly(bridge_server) -> None:
    mcp, _ = bridge_server
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    for name in ("rhino_viewport_image", "rhino_screenshot", "rhino_viewport_preview"):
        assert tools[name].annotations is not None
        # Captures may write (and overwrite) a caller-chosen file, so clients must not auto-approve.
        assert tools[name].annotations.readOnlyHint is False, name
        # The mixed Image/dict return must not produce an output schema.
        assert tools[name].outputSchema is None, name


@pytest.mark.parametrize("tool", ["rhino_viewport_image", "rhino_screenshot", "rhino_viewport_preview"])
def test_requested_image_missing_raises_with_encoder_error(tool: str) -> None:
    mcp, _ = _server("encode_error")
    with pytest.raises(Exception, match=r"no image: GDI\+ JPEG encoder unavailable"):
        _call(mcp, tool, {})


def test_legacy_plugin_without_image_suggests_plugin_update() -> None:
    mcp, _ = _server("legacy")
    with pytest.raises(Exception, match=r"(?i)update the rhino-mcp plug-in"):
        _call(mcp, "rhino_viewport_image", {})


def test_missing_image_is_fine_when_not_requested(tmp_path) -> None:
    mcp, _ = _server("legacy")
    out = str(tmp_path / "a.png")
    images, payload = _split(
        _call(mcp, "rhino_viewport_image", {"include_image": False, "output_path": out})
    )
    assert images == []
    assert "summary" in payload


def test_transparent_bg_defaults_inline_image_to_png(bridge_server) -> None:
    mcp, client = bridge_server
    images, payload = _split(_call(mcp, "rhino_viewport_image", {"transparent_bg": True}))
    assert client.calls[-1][1]["format"] == "png"
    assert images[0].mimeType == "image/png"
    assert "warnings" not in payload


def test_transparent_bg_with_explicit_jpeg_warns(bridge_server) -> None:
    mcp, client = bridge_server
    images, payload = _split(
        _call(mcp, "rhino_viewport_image", {"transparent_bg": True, "format": "jpeg"})
    )
    assert client.calls[-1][1]["format"] == "jpeg"
    assert images[0].mimeType == "image/jpeg"
    assert any("flattened onto white" in w for w in payload["warnings"])

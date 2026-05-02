# -*- coding: utf-8 -*-
"""RhinoMCPBridge -- runs inside Rhino 8 to expose RhinoCommon + Grasshopper to the MCP server.

.. deprecated::
    This Python bridge is a **legacy fallback** with limited dispatch coverage
    (~8 methods).  The C# plugin (``rhino_plugin/csharp/``) is the recommended
    bridge, supporting 130+ methods including script execution, undo/redo,
    batch modify, deformation, NURBS, SubD, extraction, control points, and
    paneling.  Install the C# plugin (``dotnet build``) and load the ``.rhp``
    in Rhino for full functionality.

Run from Rhino's command line:

    _-RunPythonScript "C:\\path\\to\\rhino_plugin\\RhinoMCPBridge.py"

The bridge listens on a platform-appropriate transport (named pipe on Windows,
unix socket on macOS/Linux, or TCP if ``RHINO_MCP_TRANSPORT_KIND=tcp``) and
speaks newline-delimited JSON-RPC 2.0. The MCP server (a separate process
running ``rhino-mcp``) connects, sends a ``rhino.ping`` to detect the bridge,
then forwards every bridge-only tool call as a JSON-RPC request whose ``method``
matches the dispatcher table below.

This script targets the CPython interpreter that ships with Rhino 8's
ScriptEditor (``rhinocode``); IronPython3 also works for the JSON-RPC transport
but cannot use the Grasshopper.Instances API in the same way.
"""

# pylint: disable=import-error
from __future__ import absolute_import, division, print_function

import json
import os
import socket
import sys
import threading
import traceback
import uuid

try:
    import Rhino  # type: ignore[import-not-found]
    import Rhino.Geometry as rg  # type: ignore[import-not-found]
    import scriptcontext as sc  # type: ignore[import-not-found]
except ImportError:
    Rhino = rg = sc = None  # allows the file to be imported outside Rhino for linting

try:
    import Grasshopper  # type: ignore[import-not-found]
except ImportError:
    Grasshopper = None  # type: ignore[assignment]


# ---------------------------------------------------------------- transport ---


def _has_unix_socket():
    """Check whether the runtime supports AF_UNIX."""
    return hasattr(socket, "AF_UNIX")


def _resolve_transport():
    kind = os.environ.get("RHINO_MCP_TRANSPORT_KIND", "").lower()
    if kind == "tcp":
        return _serve_tcp
    if kind == "pipe":
        return _serve_named_pipe
    if kind == "unix":
        if not _has_unix_socket():
            print("[RhinoMCPBridge] AF_UNIX not available; falling back to TCP")
            return _serve_tcp
        return _serve_unix
    if sys.platform == "win32":
        return _serve_named_pipe
    # macOS/Linux: prefer unix socket, fall back to TCP if unavailable.
    if _has_unix_socket():
        return _serve_unix
    print("[RhinoMCPBridge] AF_UNIX not available in this Python; using TCP")
    return _serve_tcp


def _default_socket_path():
    if "RHINO_MCP_SOCKET" in os.environ:
        return os.environ["RHINO_MCP_SOCKET"]
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return os.path.join(runtime, "rhino_mcp.sock")
    return "/tmp/rhino_mcp.sock"


def _serve_tcp(handler):
    host = os.environ.get("RHINO_HOST", "127.0.0.1")
    port = int(os.environ.get("RHINO_PORT", "4242"))
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(1)
    print("[RhinoMCPBridge] listening on tcp://%s:%d" % (host, port))
    while True:
        conn, addr = s.accept()
        threading.Thread(target=_serve_conn, args=(conn, handler)).start()


def _serve_unix(handler):
    path = _default_socket_path()
    if os.path.exists(path):
        os.unlink(path)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(path)
    s.listen(1)
    print("[RhinoMCPBridge] listening on unix://%s" % path)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=_serve_conn, args=(conn, handler)).start()


def _serve_named_pipe(handler):
    name = os.environ.get("RHINO_MCP_PIPE", "rhino_mcp")
    path = r"\\.\pipe\\" + name
    print("[RhinoMCPBridge] listening on %s (named pipe)" % path)
    try:
        import win32file  # type: ignore[import-not-found]
        import win32pipe  # type: ignore[import-not-found]
    except ImportError:
        raise RuntimeError("pywin32 is required for the named-pipe transport on Windows.")
    while True:
        h = win32pipe.CreateNamedPipe(
            path,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            win32pipe.PIPE_UNLIMITED_INSTANCES,
            65536,
            65536,
            0,
            None,
            )
        win32pipe.ConnectNamedPipe(h, None)
        threading.Thread(target=_serve_pipe_conn, args=(h, handler)).start()


def _serve_conn(conn, handler):
    buf = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                if not line:
                    continue
                resp = handler(line)
                conn.sendall(resp + b"\n")
    finally:
        conn.close()


def _serve_pipe_conn(handle, handler):
    import win32file  # type: ignore[import-not-found]

    buf = b""
    try:
        while True:
            err, data = win32file.ReadFile(handle, 4096)
            if err or not data:
                break
            buf += data
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                if not line:
                    continue
                resp = handler(line)
                win32file.WriteFile(handle, resp + b"\n")
    finally:
        try:
            win32file.CloseHandle(handle)
        except Exception:
            pass


# ----------------------------------------------------------------- dispatch ---


def _ui_thread_call(fn):
    """Marshal ``fn`` onto Rhino's UI thread and return its result."""
    if Rhino is None:
        return fn()
    result = {}

    def runner():
        try:
            result["value"] = fn()
        except Exception as exc:  # pragma: no cover - executes inside Rhino
            result["error"] = exc
            result["trace"] = traceback.format_exc()

    Rhino.RhinoApp.InvokeOnUiThread(runner)
    if "error" in result:
        raise result["error"]
    return result["value"]


def _ping(_params):
    return {
        "rhino": Rhino.RhinoApp.Version.ToString() if Rhino else "headless",
        "grasshopper": (
            Grasshopper.Versioning.Version.ToString() if Grasshopper else None
        ),
        "bridge_version": "0.1.0",
    }


def _add_sphere(params):
    centre = params["center"]
    sphere = rg.Sphere(rg.Point3d(centre["x"], centre["y"], centre["z"]), params["radius"])
    gid = sc.doc.Objects.AddSphere(sphere)
    sc.doc.Views.Redraw()
    return {"object_id": str(gid)}


def _add_box(params):
    c = params["corner"]
    plane = rg.Plane.WorldXY
    box = rg.Box(
        plane,
        rg.Interval(c["x"], c["x"] + params["size_x"]),
        rg.Interval(c["y"], c["y"] + params["size_y"]),
        rg.Interval(c["z"], c["z"] + params["size_z"]),
    )
    gid = sc.doc.Objects.AddBox(box)
    sc.doc.Views.Redraw()
    return {"object_id": str(gid)}


def _boolean_union(params):
    a_breps = _resolve_breps(params["a_ids"])
    b_breps = _resolve_breps(params["b_ids"])
    result = rg.Brep.CreateBooleanUnion(list(a_breps) + list(b_breps), sc.doc.ModelAbsoluteTolerance)
    new_ids = []
    if result is not None:
        for r in result:
            new_ids.append(str(sc.doc.Objects.AddBrep(r)))
    sc.doc.Views.Redraw()
    return {"object_ids": new_ids}


def _resolve_breps(ids):
    out = []
    for sid in ids:
        gid = uuid.UUID(sid)
        obj = sc.doc.Objects.FindId(gid)
        if obj is None:
            raise KeyError("object %s not found" % sid)
        geom = obj.Geometry
        if isinstance(geom, rg.Brep):
            out.append(geom)
        elif hasattr(geom, "ToBrep"):
            out.append(geom.ToBrep())
    return out


def _gh_doc():
    if Grasshopper is None:
        raise RuntimeError("Grasshopper is not loaded; open the Grasshopper editor first.")
    server = Grasshopper.Instances.DocumentServer
    if server.Count == 0:
        raise RuntimeError("No active Grasshopper document.")
    return server[0]


def _gh_set_slider(params):
    gh = _gh_doc()
    gid = uuid.UUID(params["component_id"])
    obj = gh.FindObject(gid, True)
    if obj is None:
        raise KeyError("Grasshopper component %s not found" % params["component_id"])
    obj.SetSliderValue(params["value"])
    obj.ExpireSolution(True)
    return {"component_id": params["component_id"], "value": params["value"]}


def _gh_run(_params):
    _gh_doc().NewSolution(True)
    return {"status": "ok"}


def _gh_bake(params):
    gh = _gh_doc()
    layer = params.get("layer")
    baked = []
    for sid in params["component_ids"]:
        gid = uuid.UUID(sid)
        obj = gh.FindObject(gid, True)
        if obj is None:
            continue
        attrs = sc.doc.CreateDefaultAttributes()
        if layer:
            attrs.LayerIndex = _ensure_layer(layer)
        for goo in obj.VolatileData.AllData(True):
            geom = getattr(goo, "Value", None)
            if geom is None:
                continue
            new_id = sc.doc.Objects.Add(geom, attrs)
            baked.append(str(new_id))
    sc.doc.Views.Redraw()
    return {"object_ids": baked}


def _ensure_layer(name):
    layer = sc.doc.Layers.FindName(name)
    if layer is None:
        layer = Rhino.DocObjects.Layer()
        layer.Name = name
        return sc.doc.Layers.Add(layer)
    return layer.Index


# Methods that fall through to Rhino's command line -- short and sweet.
def _run_command(name):
    return _ui_thread_call(lambda: Rhino.RhinoApp.RunScript(name, False))


# ---------------------------------------------------------------- registry ---


DISPATCH = {
    "rhino.ping": _ping,
    "rhino.solid.sphere": lambda p: _ui_thread_call(lambda: _add_sphere(p)),
    "rhino.solid.box": lambda p: _ui_thread_call(lambda: _add_box(p)),
    "rhino.solid.boolean_union": lambda p: _ui_thread_call(lambda: _boolean_union(p)),
    "rhino.display.zoom_extent": lambda p: _ui_thread_call(
        lambda: ({"status": "ok", "ran": _run_command("_Zoom _Extents")})
    ),
    "gh.canvas.run": lambda p: _ui_thread_call(lambda: _gh_run(p)),
    "gh.parameter.set_slider": lambda p: _ui_thread_call(lambda: _gh_set_slider(p)),
    "gh.canvas.bake": lambda p: _ui_thread_call(lambda: _gh_bake(p)),
}


def handle(line):
    try:
        request = json.loads(line.decode("utf-8"))
    except Exception as exc:
        return _err(None, -32700, "Parse error: %s" % exc)
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    handler = DISPATCH.get(method)
    if handler is None:
        return _err(request_id, -32601, "Method not found: %s" % method)
    try:
        result = handler(params)
    except Exception as exc:
        tb = traceback.format_exc()
        return _err(request_id, -32000, str(exc), {"trace": tb})
    return _ok(request_id, result)


def _ok(request_id, result):
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}).encode("utf-8")


def _err(request_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "error": err}).encode("utf-8")


# ----------------------------------------------------------------- bootstrap ---


def main():
    serve = _resolve_transport()
    # Run the listener in a daemon thread so Rhino's main / UI thread stays
    # responsive.  A blocking accept() on the main thread causes SIGABRT on
    # macOS because Rhino can no longer service Cocoa run-loop events.
    t = threading.Thread(target=serve, args=(handle,))
    t.daemon = True
    t.start()
    print("[RhinoMCPBridge] bridge thread started (daemon)")


if __name__ == "__main__":
    main()

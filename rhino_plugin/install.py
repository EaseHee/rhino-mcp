"""Install RhinoMCPBridge.py as a Rhino startup script.

Detects the platform-appropriate ``startup`` directory and copies the bridge
script in. Run with the same Python interpreter Rhino uses (or any CPython 3.x).

Locations:

* Windows: ``%APPDATA%\\McNeel\\Rhinoceros\\8.0\\scripts``
* macOS:   ``~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts``
* Linux:   ``~/.config/Rhino/8.0/scripts`` (Rhino on Linux is unofficial; honoured
  if the path exists).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
SOURCE = THIS_DIR / "RhinoMCPBridge.py"


def script_dir() -> Path:
    if sys.platform == "win32":
        appdata = Path.home() / "AppData" / "Roaming"
        return appdata / "McNeel" / "Rhinoceros" / "8.0" / "scripts"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "McNeel" / "Rhinoceros" / "8.0" / "scripts"
    return Path.home() / ".config" / "Rhino" / "8.0" / "scripts"


def main() -> int:
    target_dir = script_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "RhinoMCPBridge.py"
    shutil.copy2(SOURCE, target)
    print(f"Installed RhinoMCPBridge.py → {target}")
    print(
        "In Rhino 8 run:\n"
        f"    _-RunPythonScript \"{target}\"\n"
        "to launch the bridge listener."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

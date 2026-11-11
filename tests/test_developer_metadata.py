"""Developer contact info has one source: ``rhino_plugin/csharp/RhinoMCPPlugin.csproj``.

The plug-in's ``PlugInDescription`` attributes and the Yak manifest derive from it at build time.
``pyproject.toml`` metadata is static, so these tests keep it in step instead.
"""

from __future__ import annotations

import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSPROJ = ROOT / "rhino_plugin" / "csharp" / "RhinoMCPPlugin.csproj"
MANIFEST = ROOT / "rhino_plugin" / "csharp" / "manifest.yml"
PYPROJECT = ROOT / "pyproject.toml"

# Rhino 9 refuses to install a plug-in missing these.
REQUIRED_DESCRIPTIONS = {"Organization", "Email", "WebSite", "UpdateUrl", "Country"}


def _csproj() -> ET.Element:
    return ET.parse(CSPROJ).getroot()


def _property(name: str) -> str:
    node = _csproj().find(f"./PropertyGroup/{name}")
    assert node is not None and node.text, f"{name} missing from {CSPROJ.name}"
    return node.text.strip()


def test_csproj_declares_every_required_plugin_description() -> None:
    declared = set()
    for attr in _csproj().iterfind("./ItemGroup/AssemblyAttribute"):
        if attr.get("Include") != "Rhino.PlugIns.PlugInDescriptionAttribute":
            continue
        kind = attr.findtext("_Parameter1", "").rsplit(".", 1)[-1]
        value = attr.findtext("_Parameter2", "").strip()
        assert value, f"PlugInDescription {kind} has an empty value"
        declared.add(kind)
    assert declared == REQUIRED_DESCRIPTIONS


def test_no_hand_written_plugin_description() -> None:
    sources = (CSPROJ.parent).rglob("*.cs")
    offenders = [
        p
        for p in sources
        if "obj" not in p.parts and "bin" not in p.parts and "PlugInDescription" in p.read_text("utf-8")
    ]
    assert offenders == []


def test_pyproject_author_matches_csproj() -> None:
    meta = tomllib.loads(PYPROJECT.read_text("utf-8"))["project"]
    assert meta["authors"] == [{"name": _property("DeveloperName"), "email": _property("DeveloperEmail")}]


def test_pyproject_urls_use_csproj_repository() -> None:
    repo = _property("RepositoryUrl")
    urls = tomllib.loads(PYPROJECT.read_text("utf-8"))["project"]["urls"]
    assert urls, "pyproject has no [project.urls]"
    for key, url in urls.items():
        assert url == repo or url.startswith(repo + "/"), f"{key} = {url} does not start with {repo}"


def test_manifest_takes_developer_info_from_placeholders() -> None:
    text = MANIFEST.read_text("utf-8")
    assert '- "{{DEVELOPER_NAME}} <{{DEVELOPER_EMAIL}}>"' in text
    assert 'url: "{{REPOSITORY_URL}}"' in text
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), "manifest hard-codes an email address"
    assert "github.com/" not in text, "manifest hard-codes a repository URL"

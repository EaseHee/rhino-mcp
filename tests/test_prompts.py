"""MCP prompt registration tests."""

from __future__ import annotations

from rhino_mcp.prompts import strategy


def _get_prompts(mcp):
    """Extract registered prompts from FastMCP's internal manager (test helper)."""
    mgr = getattr(mcp, "_prompt_manager", None)
    if mgr is not None:
        return mgr._prompts  # type: ignore[attr-defined]
    return {}


def test_strategy_module_exports_seven_prompts() -> None:
    assert callable(strategy.general_strategy)
    assert callable(strategy.rhinoscript_workflow)
    assert callable(strategy.viewport_workflow)
    assert callable(strategy.parametric_workflow)
    assert callable(strategy.bim_authoring_workflow)
    assert callable(strategy.design_dialogue_workflow)
    assert callable(strategy.freeform_workflow)


def test_general_strategy_references_real_tools() -> None:
    text = strategy.general_strategy()
    # Decision tree must point at the actual rhino_* tool names this server exposes.
    for tool in (
        "rhino_document_summary",
        "rhino_layer_list",
        "rhino_list_objects",
        "rhino_object_select",
        "rhino_screenshot",
        "rhino_execute_python",
    ):
        assert tool in text, f"general_strategy missing reference to {tool}"


def test_rhinoscript_workflow_emphasises_doc_lookup() -> None:
    text = strategy.rhinoscript_workflow()
    assert "rhino_search_rhinoscript_functions" in text
    assert "rhino_get_rhinoscript_docs" in text
    assert "rhino_execute_python" in text


def test_viewport_workflow_calls_out_base64() -> None:
    text = strategy.viewport_workflow()
    assert "rhino_zoom_extent" in text
    assert "rhino_screenshot" in text
    assert "as_base64" in text


def test_prompts_registered_on_server(server_standalone) -> None:
    mcp, _tools = server_standalone
    prompts = _get_prompts(mcp)
    expected = {
        "general_strategy",
        "rhinoscript_workflow",
        "viewport_workflow",
        "parametric_workflow",
        "bim_authoring_workflow",
        "design_dialogue_workflow",
        "freeform_workflow",
    }
    assert expected.issubset(prompts.keys()), (
        f"missing prompts: {expected - prompts.keys()}, got: {set(prompts.keys())}"
    )


def test_parametric_workflow_covers_units_and_validation() -> None:
    text = strategy.parametric_workflow()
    assert "rhino_document_summary" in text
    assert "rhino_validate_brep" in text
    assert "rhino_screenshot" in text
    assert "seed" in text


def test_bim_authoring_workflow_covers_layer_and_user_text() -> None:
    text = strategy.bim_authoring_workflow()
    assert "rhino_layer_create" in text
    assert "rhino_set_user_text" in text
    assert "rhino_object_select" in text
    assert "function" in text


def test_design_dialogue_workflow_covers_checkpoints() -> None:
    text = strategy.design_dialogue_workflow()
    assert "rhino_zoom_extent" in text
    assert "rhino_named_view_save" in text or "named_view_save" in text
    assert "rhino_set_user_text" in text


def test_freeform_workflow_covers_panel_classification() -> None:
    text = strategy.freeform_workflow()
    assert "rhino_skin_from_sections" in text
    assert "rhino_uv_grid_panels" in text
    assert "rhino_panel_planarity" in text
    assert "rhino_panel_curvature_classify" in text
    assert "rhino_surface_developable_score" in text
    assert "rhino_attractor_displace_points" in text
    assert "rhino_smooth_polyline" in text

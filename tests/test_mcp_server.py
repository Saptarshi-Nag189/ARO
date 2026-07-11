"""MCP server smoke tests — in-process FastMCP client, offline fake model."""

import asyncio
import json

import pytest


@pytest.fixture(scope="module")
def mcp_instance():
    from mcp_server.server import mcp
    return mcp


def _call(mcp_instance, tool, args):
    from fastmcp import Client

    async def _run():
        async with Client(mcp_instance) as client:
            result = await client.call_tool(tool, args)
            return result

    return asyncio.run(_run())


def test_tools_are_registered(mcp_instance):
    from fastmcp import Client

    async def _run():
        async with Client(mcp_instance) as client:
            return [t.name for t in await client.list_tools()]

    names = asyncio.run(_run())
    assert {"fast_research", "deep_research",
            "list_research_sessions", "get_research_report"} <= set(names)


def test_fast_research_tool_returns_answer(mcp_instance):
    result = _call(mcp_instance, "fast_research", {"question": "MCP smoke question"})
    payload = json.loads(result.content[0].text)
    assert payload["answer"]
    assert payload["session_id"].startswith("session_")
    assert 0.0 <= payload["confidence"] <= 1.0


def test_report_roundtrip_via_tool_and_resource(mcp_instance):
    result = _call(mcp_instance, "fast_research", {"question": "Roundtrip question"})
    session_id = json.loads(result.content[0].text)["session_id"]

    report = _call(mcp_instance, "get_research_report", {"session_id": session_id})
    payload = json.loads(report.content[0].text)
    assert payload["research_objective"] == "Roundtrip question"

    from fastmcp import Client

    async def _read():
        async with Client(mcp_instance) as client:
            return await client.read_resource(f"aro://reports/{session_id}")

    resource = asyncio.run(_read())
    assert "Roundtrip question" in resource[0].text


def test_invalid_session_id_rejected(mcp_instance):
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        _call(mcp_instance, "get_research_report",
              {"session_id": "../../etc/passwd"})


def test_sessions_listing_includes_new_run(mcp_instance):
    result = _call(mcp_instance, "list_research_sessions", {"limit": 50})
    sessions = json.loads(result.content[0].text)
    if isinstance(sessions, dict):  # fastmcp may wrap lists
        sessions = sessions.get("result", sessions)
    objectives = [s["objective"] for s in sessions]
    assert "MCP smoke question" in objectives

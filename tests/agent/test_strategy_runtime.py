"""Behavior contracts for executable skill strategy runtime."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agent import strategy_runtime
from agent.execution_authority import TurnCapability
from agent.strategy_runtime import (
    StrategyContractError,
    activate_strategy_message,
    discover_strategy_indexes,
    execute_active_strategy,
    load_strategy_manifest,
    reset_active_strategies,
    set_active_strategies_from_message,
)
from hermes_state import SessionDB
from tools.registry import ToolRegistry


def _skill(tmp_path: Path, manifest: str) -> tuple[Path, Path]:
    skill_dir = tmp_path / "skills" / "demo-skill"
    strategies_dir = skill_dir / "strategies"
    strategies_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        """---
name: demo-skill
description: Runs a deterministic demo.
metadata:
  hermes:
    strategies:
      version: 1
      capabilities:
        - id: demo.echo
          manifest: strategies/echo.yaml
---
# Demo
""",
        encoding="utf-8",
    )
    manifest_path = strategies_dir / "echo.yaml"
    manifest_path.write_text(manifest, encoding="utf-8")
    return skill_dir, skill_md


def _manifest(
    *,
    operation: str = "demo.echo",
    outcome: str = "ok",
    input_name: str = "text",
) -> str:
    return yaml.safe_dump(
        {
            "schema_version": 1,
            "capability": "demo.echo",
            "start": "send",
            "max_steps": 2,
            "nodes": {
                "send": {
                    "mode": "contracted",
                    "operation": operation,
                    "bindings": {input_name: {"input": input_name}},
                    "outcomes": {outcome: {"terminal": "success"}},
                }
            },
        },
        sort_keys=False,
    )


def _registry(*, available: bool = True, outcome: str = "ok") -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        name="demo_echo_tool",
        toolset="demo",
        schema={
            "name": "demo_echo_tool",
            "description": "Echo through a normalized contract operation.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
        },
        handler=lambda args, **kwargs: json.dumps(
            {"outcome": outcome, "echo": args["text"]}
        ),
        check_fn=lambda: available,
        contract_operation="demo.echo",
        normalized_outcomes={"ok", "rejected"},
    )
    return registry


def test_discovery_reads_compact_index_without_loading_manifest(tmp_path, monkeypatch):
    skill_dir, _ = _skill(tmp_path, "this: [is: deliberately: malformed")
    manifest_path = skill_dir / "strategies" / "echo.yaml"
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args, **kwargs):
        if path == manifest_path:
            raise AssertionError("discovery eagerly loaded the strategy manifest")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    indexes = discover_strategy_indexes([tmp_path / "skills"])

    assert indexes == [
        {
            "skill": "demo-skill",
            "skill_root": str(skill_dir.resolve()),
            "index_version": 1,
            "capability": "demo.echo",
            "manifest": "strategies/echo.yaml",
        }
    ]


def test_manifest_load_is_lazy_and_path_contained(tmp_path):
    skill_dir, _ = _skill(tmp_path, _manifest())

    loaded = load_strategy_manifest(skill_dir, "strategies/echo.yaml")

    assert loaded["capability"] == "demo.echo"
    assert loaded["nodes"]["send"]["operation"] == "demo.echo"
    with pytest.raises(StrategyContractError, match="outside skill root"):
        load_strategy_manifest(skill_dir, "../escape.yaml")


def test_registry_contract_operation_dispatches_normalized_outcome():
    registry = _registry()

    result = json.loads(registry.dispatch_contract_operation("demo.echo", {"text": "hi"}))

    assert result == {"outcome": "ok", "echo": "hi"}
    assert registry.contract_operation_available("demo.echo") is True


def test_real_read_file_contract_normalizes_without_changing_adaptive_output(tmp_path):
    from tools.file_tools import _handle_read_file
    from tools.registry import registry

    fixture = tmp_path / "fixture.txt"
    fixture.write_text("contract fixture\n", encoding="utf-8")
    args = {"path": str(fixture), "offset": 1, "limit": 10}

    adaptive = json.loads(
        _handle_read_file(args, task_id="adaptive-read-contract-test")
    )
    contracted = json.loads(
        registry.dispatch_contract_operation(
            "file.read",
            args,
            task_id="contracted-read-contract-test",
        )
    )

    assert "outcome" not in adaptive
    assert contracted["outcome"] == "ok"
    assert contracted["content"] == adaptive["content"]


def test_contracted_execution_validates_before_side_effect_and_uses_bound_inputs(tmp_path):
    skill_dir, skill_md = _skill(tmp_path, _manifest())
    raw_skill = skill_md.read_text(encoding="utf-8")
    message = activate_strategy_message("expanded skill body", raw_skill, skill_dir)
    activation_token = set_active_strategies_from_message(message)
    registry = _registry()

    try:
        result = execute_active_strategy(
            capability="demo.echo",
            inputs={"text": "hello"},
            registry=registry,
            authority_capabilities=frozenset({TurnCapability.CONTRACT_EXECUTE}),
        )
    finally:
        reset_active_strategies(activation_token)

    assert result["status"] == "success"
    assert result["execution_mode"] == "contracted"
    assert result["terminal_state"] == "success"
    assert result["result"]["echo"] == "hello"
    assert result["steps"] == [
        {
            "node": "send",
            "operation": "demo.echo",
            "outcome": "ok",
            "transition": "terminal:success",
        }
    ]
    assert result["manifest_digest"]
    assert result["result"] == {"outcome": "ok", "echo": "hello"}


def test_unavailable_operation_is_not_misclassified_as_contract_gap(tmp_path):
    skill_dir, skill_md = _skill(tmp_path, _manifest())
    message = activate_strategy_message(
        "expanded skill body", skill_md.read_text(encoding="utf-8"), skill_dir
    )
    activation_token = set_active_strategies_from_message(message)

    try:
        result = execute_active_strategy(
            capability="demo.echo",
            inputs={"text": "hello"},
            registry=_registry(available=False),
            authority_capabilities=frozenset({TurnCapability.CONTRACT_EXECUTE}),
        )
    finally:
        reset_active_strategies(activation_token)

    assert result["status"] == "unavailable"
    assert result["error_type"] == "operation_unavailable"
    assert result["steps"] == []


def test_unknown_normalized_outcome_fails_closed_without_fallback(tmp_path):
    skill_dir, skill_md = _skill(tmp_path, _manifest())
    message = activate_strategy_message(
        "expanded skill body", skill_md.read_text(encoding="utf-8"), skill_dir
    )
    activation_token = set_active_strategies_from_message(message)

    try:
        result = execute_active_strategy(
            capability="demo.echo",
            inputs={"text": "hello"},
            registry=_registry(outcome="new_backend_state"),
            authority_capabilities=frozenset({TurnCapability.CONTRACT_EXECUTE}),
        )
    finally:
        reset_active_strategies(activation_token)

    assert result["status"] == "contract_gap"
    assert result["error_type"] == "unknown_normalized_outcome"
    assert result["steps"][0]["outcome"] == "new_backend_state"


def test_strategy_trace_round_trips_outside_role_stream(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session("session-1", "test")
    trace = {
        "status": "success",
        "capability": "demo.echo",
        "manifest_digest": "abc123",
        "steps": [{"node": "send", "outcome": "ok"}],
    }

    trace_id = db.append_strategy_trace("session-1", trace)

    stored = db.get_strategy_traces("session-1")
    assert trace_id
    assert stored[0]["trace"] == trace
    assert db.get_messages("session-1") == []
    db.close()


def test_strategy_interface_is_service_gated_and_does_not_accept_authority():
    from agent.strategy_runtime import (
        STRATEGY_EXECUTE_SCHEMA,
        strategy_execute_service_available,
    )

    properties = STRATEGY_EXECUTE_SCHEMA["parameters"]["properties"]
    assert "authority" not in properties
    assert strategy_execute_service_available(platform="tui") is True
    assert strategy_execute_service_available(platform="cli") is False
    assert strategy_execute_service_available(platform="telegram") is False
    assert strategy_execute_service_available(platform="teams_mtk") is False


def test_strategy_service_gate_uses_trusted_tui_authority_for_cli_agent_platform():
    from agent.strategy_runtime import strategy_execute_service_available
    from gateway.session_context import clear_session_vars, set_session_vars

    session_tokens = set_session_vars(source="tui")
    try:
        assert strategy_execute_service_available(platform="cli") is True
    finally:
        clear_session_vars(session_tokens)


def test_explicit_activation_executes_and_persists_trace_via_agent_boundary(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from agent.strategy_runtime import execute_strategy_for_agent
    from gateway.session_context import clear_session_vars, set_session_vars
    from tools.registry import registry

    skill_dir, skill_md = _skill(tmp_path, _manifest())
    message = activate_strategy_message(
        "expanded skill body", skill_md.read_text(encoding="utf-8"), skill_dir
    )
    activation_token = set_active_strategies_from_message(message)
    session_tokens = set_session_vars(source="tui")
    db = SessionDB(db_path=tmp_path / "e2e.db")
    db.create_session("e2e-session", "tui")
    agent = SimpleNamespace(
        _session_db=db,
        session_id="e2e-session",
        valid_tool_names={"strategy_e2e_echo"},
        _invoke_tool=lambda name, args, task_id, **kwargs: registry.dispatch(
            name,
            args,
            task_id=task_id,
            **kwargs,
        ),
    )
    operation_calls = []

    registry.register(
        name="strategy_e2e_echo",
        toolset="test",
        schema={"name": "strategy_e2e_echo", "parameters": {"type": "object"}},
        handler=lambda args, **_kwargs: operation_calls.append(args)
        or json.dumps({"outcome": "ok", "echo": args["text"]}),
        contract_operation="demo.echo",
        normalized_outcomes={"ok"},
    )
    try:
        result = json.loads(
            execute_strategy_for_agent(
                agent,
                {
                    "capability": "demo.echo",
                    "intent_relation": "new",
                    "inputs": {"text": "hello"},
                },
            )
        )
    finally:
        registry.deregister("strategy_e2e_echo")
        clear_session_vars(session_tokens)
        reset_active_strategies(activation_token)

    assert result["status"] == "success"
    assert operation_calls == [{"text": "hello"}]
    stored = db.get_strategy_traces("e2e-session")
    assert stored[0]["trace"]["manifest_digest"] == result["manifest_digest"]
    assert stored[0]["trace"]["intent_relation"] == "new"
    assert db.get_messages("e2e-session") == []
    db.close()


def test_agent_boundary_fails_closed_without_policy_dispatcher(tmp_path):
    from types import SimpleNamespace

    from agent.strategy_runtime import execute_strategy_for_agent
    from gateway.session_context import clear_session_vars, set_session_vars
    from tools.registry import registry

    skill_dir, skill_md = _skill(tmp_path, _manifest())
    message = activate_strategy_message(
        "expanded skill body", skill_md.read_text(encoding="utf-8"), skill_dir
    )
    activation_token = set_active_strategies_from_message(message)
    session_tokens = set_session_vars(source="tui")
    operation_calls = []

    registry.register(
        name="strategy_policy_guard",
        toolset="test",
        schema={"name": "strategy_policy_guard", "parameters": {"type": "object"}},
        handler=lambda args, **_kwargs: operation_calls.append(args)
        or json.dumps({"outcome": "ok"}),
        contract_operation="demo.echo",
        normalized_outcomes={"ok"},
    )
    try:
        result = json.loads(
            execute_strategy_for_agent(
                SimpleNamespace(_session_db=None, session_id=None),
                {
                    "capability": "demo.echo",
                    "intent_relation": "new",
                    "inputs": {"text": "hello"},
                },
            )
        )
    finally:
        registry.deregister("strategy_policy_guard")
        clear_session_vars(session_tokens)
        reset_active_strategies(activation_token)

    assert result["status"] == "failed"
    assert result["error_type"] == "provider_contract_error"
    assert "policy dispatcher" in result["error"]
    assert operation_calls == []


def test_agent_boundary_does_not_report_success_when_trace_persistence_fails(
    tmp_path,
):
    from types import SimpleNamespace

    from agent.strategy_runtime import execute_strategy_for_agent
    from gateway.session_context import clear_session_vars, set_session_vars
    from tools.registry import registry

    class FailingTraceDB:
        def append_strategy_trace(self, _session_id, _trace):
            raise OSError("disk unavailable")

    skill_dir, skill_md = _skill(tmp_path, _manifest())
    message = activate_strategy_message(
        "expanded skill body", skill_md.read_text(encoding="utf-8"), skill_dir
    )
    activation_token = set_active_strategies_from_message(message)
    session_tokens = set_session_vars(source="tui")
    operation_calls = []
    agent = SimpleNamespace(
        _session_db=FailingTraceDB(),
        session_id="trace-failure-session",
        valid_tool_names={"strategy_trace_failure"},
        _invoke_tool=lambda name, args, task_id, **kwargs: registry.dispatch(
            name,
            args,
            task_id=task_id,
            **kwargs,
        ),
    )

    registry.register(
        name="strategy_trace_failure",
        toolset="test",
        schema={"name": "strategy_trace_failure", "parameters": {"type": "object"}},
        handler=lambda args, **_kwargs: operation_calls.append(args)
        or json.dumps({"outcome": "ok", "echo": args["text"]}),
        contract_operation="demo.echo",
        normalized_outcomes={"ok"},
    )
    try:
        result = json.loads(
            execute_strategy_for_agent(
                agent,
                {
                    "capability": "demo.echo",
                    "intent_relation": "new",
                    "inputs": {"text": "hello"},
                },
            )
        )
    finally:
        registry.deregister("strategy_trace_failure")
        clear_session_vars(session_tokens)
        reset_active_strategies(activation_token)

    assert operation_calls == [{"text": "hello"}]
    assert result["status"] == "failed"
    assert result["terminal_state"] == "failed"
    assert result["error_type"] == "trace_persistence_error"
    assert result["operation_completed"] is True
    assert "result" not in result
    assert "disk unavailable" not in result["error"]


def test_contracted_execution_accepts_normalized_mapping_results(tmp_path):
    skill_dir, skill_md = _skill(tmp_path, _manifest())

    class MappingRegistry:
        def has_contract_operation(self, operation: str) -> bool:
            return operation == "demo.echo"

        def get_contract_outcomes(self, operation: str) -> set[str]:
            assert operation == "demo.echo"
            return {"ok"}

        def contract_operation_available(self, operation: str) -> bool:
            return operation == "demo.echo"

        def dispatch_contract_operation(
            self, operation: str, arguments: dict[str, object]
        ) -> dict[str, object]:
            assert operation == "demo.echo"
            return {"outcome": "ok", "echo": arguments["text"]}

    message = activate_strategy_message(
        "expanded skill body", skill_md.read_text(encoding="utf-8"), skill_dir
    )
    activation_token = set_active_strategies_from_message(message)
    try:
        result = execute_active_strategy(
            capability="demo.echo",
            inputs={"text": "hello"},
            registry=cast(Any, MappingRegistry()),
            authority_capabilities=frozenset({TurnCapability.CONTRACT_EXECUTE}),
        )
    finally:
        reset_active_strategies(activation_token)

    assert result["status"] == "success"
    assert result["steps"][0]["outcome"] == "ok"


def test_adaptive_node_returns_bounded_handoff_without_provider_dispatch(tmp_path):
    manifest = yaml.safe_load(_manifest())
    manifest["start"] = "judge"
    manifest["nodes"] = {
        "judge": {
            "mode": "adaptive",
            "objective": "classify the ambiguous user intent",
        }
    }
    skill_dir, skill_md = _skill(tmp_path, yaml.safe_dump(manifest, sort_keys=False))
    message = activate_strategy_message(
        "expanded skill body", skill_md.read_text(encoding="utf-8"), skill_dir
    )
    activation_token = set_active_strategies_from_message(message)
    registry = _registry()
    try:
        result = execute_active_strategy(
            capability="demo.echo",
            inputs={"text": "hello"},
            registry=registry,
            authority_capabilities=frozenset({TurnCapability.CONTRACT_EXECUTE}),
        )
    finally:
        reset_active_strategies(activation_token)

    assert result["status"] == "handoff"
    assert result["execution_mode"] == "adaptive"
    assert result["terminal_state"] == "handoff"
    assert result["error_type"] == "adaptive_handoff"
    assert result["steps"] == []


def _mock_tool_call(name: str, arguments: dict, call_id: str = "strategy-1"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def _mock_response(content: str = "", tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(
        message=message,
        finish_reason="tool_calls" if tool_calls else "stop",
    )
    return SimpleNamespace(choices=[choice], model="test/model", usage=None)


def _tool_definition(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} test tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _make_strategy_agent(
    *,
    tool_defs: list[dict],
    session_db,
    session_id: str,
    platform: str = "tui",
) -> Any:
    from run_agent import AIAgent

    with (
        patch("run_agent.get_tool_definitions", return_value=tool_defs),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
        patch("agent.model_metadata.fetch_model_metadata", return_value={}),
    ):
        agent = AIAgent(
            api_key="test-key",
            base_url="https://example.invalid/v1",
            platform=platform,
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            session_db=session_db,
            session_id=session_id,
            max_iterations=3,
        )
    agent.client = MagicMock()
    agent._cached_system_prompt = "You are helpful."
    agent._use_prompt_caching = False
    agent.tool_delay = 0
    agent.compression_enabled = False
    agent.save_trajectories = False
    return agent


@pytest.mark.parametrize(
    ("platform", "strategies_available"),
    [("telegram", True), ("cli", True), ("tui", False)],
)
def test_agent_construction_omits_strategy_interface_when_gate_is_closed(
    tmp_path, monkeypatch, platform, strategies_available
):
    monkeypatch.setattr(
        "agent.strategy_runtime.executable_strategies_available",
        lambda: strategies_available,
    )
    db = SessionDB(db_path=tmp_path / "state.db")
    try:
        agent = _make_strategy_agent(
            tool_defs=[_tool_definition("read_file")],
            session_db=db,
            session_id="strategy-gate",
            platform=platform,
        )
        agent = cast(Any, agent)

        assert "strategy_execute" not in agent.valid_tool_names
        assert all(
            tool["function"]["name"] != "strategy_execute"
            for tool in agent.tools
        )
    finally:
        db.close()


def test_strategy_tool_collision_cannot_bypass_closed_gate(monkeypatch):
    agent = SimpleNamespace(
        platform="telegram",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "strategy_execute",
                    "description": "registry collision",
                    "parameters": {},
                },
            }
        ],
        valid_tool_names={"strategy_execute"},
    )
    monkeypatch.setattr(strategy_runtime, "executable_strategies_available", lambda: True)

    strategy_runtime.attach_strategy_execute_tool(agent)

    assert "strategy_execute" not in agent.valid_tool_names
    assert all(
        tool["function"]["name"] != "strategy_execute"
        for tool in agent.tools
    )
    assert agent._construction_static_tools == ()


def test_strategy_tool_owns_its_reserved_schema(monkeypatch):
    agent = SimpleNamespace(
        platform="tui",
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "strategy_execute",
                    "description": "registry collision",
                    "parameters": {},
                },
            }
        ],
        valid_tool_names={"strategy_execute"},
    )
    monkeypatch.setattr(strategy_runtime, "executable_strategies_available", lambda: True)

    strategy_runtime.attach_strategy_execute_tool(agent)

    matching = [
        tool
        for tool in agent.tools
        if tool["function"]["name"] == "strategy_execute"
    ]
    assert matching == [
        {"type": "function", "function": strategy_runtime.STRATEGY_EXECUTE_SCHEMA}
    ]
    assert agent._construction_static_tools == tuple(matching)


def test_contract_execution_authority_is_tui_only(monkeypatch):
    from agent.execution_authority import TurnCapability, current_execution_authority
    from gateway.session_context import clear_session_vars, set_session_vars

    for key in (
        "HERMES_SESSION_PLATFORM",
        "HERMES_SESSION_SOURCE",
        "HERMES_SESSION_CHAT_ID",
        "HERMES_SESSION_USER_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    cli_tokens = set_session_vars(
        platform="local",
        source="cli",
        chat_id="",
        user_id="",
        session_key="cli:strategy-authority",
    )
    try:
        classic_cli = current_execution_authority()
    finally:
        clear_session_vars(cli_tokens)

    assert classic_cli.allows(TurnCapability.SKILL_WRITE)
    assert not classic_cli.allows(TurnCapability.CONTRACT_EXECUTE)

    tokens = set_session_vars(
        platform="",
        source="tui",
        chat_id="",
        user_id="",
        session_key="tui:strategy-authority",
    )
    try:
        tui = current_execution_authority()
    finally:
        clear_session_vars(tokens)

    assert tui.allows(TurnCapability.SKILL_WRITE)
    assert tui.allows(TurnCapability.CONTRACT_EXECUTE)


def test_real_read_file_contract_normalizes_failure_outcomes(tmp_path, monkeypatch):
    from tools import file_tools  # noqa: F401 - imports the built-in registration
    from tools.registry import registry

    missing_raw = registry.dispatch_contract_operation(
        "file.read",
        {"path": str(tmp_path / "missing.txt")},
        task_id="strategy-missing-file",
    )
    assert isinstance(missing_raw, str)
    missing = json.loads(missing_raw)

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    denied_raw = registry.dispatch_contract_operation(
        "file.read",
        {"path": str(hermes_home / "auth.json")},
        task_id="strategy-denied-file",
    )
    assert isinstance(denied_raw, str)
    denied = json.loads(denied_raw)

    assert missing["outcome"] == "not_found"
    assert missing["error"]
    assert denied["outcome"] == "denied"
    assert denied["error"]


def test_run_conversation_executes_activated_strategy_and_persists_trace(
    tmp_path, monkeypatch
):
    from agent import skill_commands
    from gateway.session_context import clear_session_vars, set_session_vars
    from tools import skills_tool
    home = tmp_path / ".hermes"
    fixture = tmp_path / "fixture.txt"
    fixture.write_text("hello from real read_file\n", encoding="utf-8")
    skill_dir, _ = _skill(
        home,
        _manifest(operation="file.read", input_name="path"),
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(skills_tool, "SKILLS_DIR", home / "skills")
    skill_commands._skill_commands = {}
    skill_commands._skill_commands_platform = None

    db = SessionDB(db_path=tmp_path / "state.db")
    session_tokens = set_session_vars(source="tui")
    try:
        user_message = skill_commands.build_skill_invocation_message(
            "/demo-skill", "Read the fixture", task_id="strategy-e2e-task"
        )
        assert user_message is not None
        assert str(skill_dir.resolve()) in user_message

        agent = _make_strategy_agent(
            tool_defs=[_tool_definition("read_file")],
            session_db=db,
            session_id="strategy-e2e",
        )
        assert "strategy_execute" in agent.valid_tool_names
        agent.client.chat.completions.create.side_effect = [
            _mock_response(
                tool_calls=[
                    _mock_tool_call(
                        "strategy_execute",
                        {
                            "capability": "demo.echo",
                            "inputs": {"path": str(fixture)},
                            "intent_relation": "new",
                            "intent_reference": "fixture-intent",
                        },
                    )
                ]
            ),
            _mock_response(content="done"),
        ]

        with (
            patch.object(agent, "_save_trajectory"),
            patch.object(agent, "_cleanup_task_resources"),
        ):
            result = agent.run_conversation(
                user_message, task_id="strategy-e2e-task"
            )

        traces = db.get_strategy_traces("strategy-e2e")
        strategy_tool_messages = [
            message
            for message in result["messages"]
            if message.get("role") == "tool"
            and message.get("name") == "strategy_execute"
        ]
        strategy_result = json.loads(strategy_tool_messages[0]["content"])
        assert result["final_response"] == "done"
        assert agent.client.chat.completions.create.call_count == 2
        assert len(strategy_tool_messages) == 1
        assert "hello from real read_file" in strategy_result["result"]["content"]
        assert len(traces) == 1
        assert traces[0]["trace"]["status"] == "success"
        assert traces[0]["trace"]["capability"] == "demo.echo"
        assert traces[0]["trace"]["execution_mode"] == "contracted"
        assert traces[0]["trace"]["terminal_state"] == "success"
        assert traces[0]["trace"]["manifest_digest"]
        assert traces[0]["trace"]["steps"] == [
            {
                "node": "send",
                "operation": "file.read",
                "outcome": "ok",
                "transition": "terminal:success",
            }
        ]
        assert traces[0]["trace"]["budget"] == {
            "max_steps": 2,
            "steps_used": 1,
        }
        assert "result" not in traces[0]["trace"]
    finally:
        clear_session_vars(session_tokens)
        db.close()
        skill_commands._skill_commands = {}
        skill_commands._skill_commands_platform = None


def test_run_conversation_without_activation_remains_adaptive(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agent.strategy_runtime.executable_strategies_available", lambda: True
    )
    db = SessionDB(db_path=tmp_path / "state.db")
    try:
        agent = _make_strategy_agent(
            tool_defs=[_tool_definition("read_file")],
            session_db=db,
            session_id="adaptive-e2e",
        )
        assert "strategy_execute" in agent.valid_tool_names
        agent.client.chat.completions.create.return_value = _mock_response(
            content="adaptive answer"
        )

        with (
            patch.object(agent, "_save_trajectory"),
            patch.object(agent, "_cleanup_task_resources"),
        ):
            result = agent.run_conversation(
                "Read normally without loading a skill", task_id="adaptive-task"
            )

        assert result["final_response"] == "adaptive answer"
        assert db.get_strategy_traces("adaptive-e2e") == []
    finally:
        db.close()

"""Lazy-loaded, data-only executable skill strategy contracts.

Discovery reads only the compact index in ``SKILL.md`` frontmatter. Full YAML
manifests are resolved below the owning skill root and validated before the
first provider operation is dispatched.
"""

from __future__ import annotations

import contextvars
import hmac
import hashlib
import json
import logging
import re
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from agent.skill_utils import iter_skill_index_files


logger = logging.getLogger(__name__)


STRATEGY_INDEX_START = "[HERMES_STRATEGY_INDEX]"
STRATEGY_INDEX_END = "[/HERMES_STRATEGY_INDEX]"
_SUPPORTED_INDEX_VERSION = 1
_SUPPORTED_MANIFEST_VERSION = 1
_INDEX_SIGNING_KEY = secrets.token_bytes(32)
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_FORBIDDEN_MANIFEST_KEYS = {
    "script",
    "shell",
    "command",
    "code",
    "credential",
    "credentials",
    "password",
    "token",
    "secret",
}
_TERMINAL_RESULTS = {
    "success",
    "failed",
    "blocked",
    "partial",
    "cancelled",
}


class StrategyContractError(ValueError):
    """The strategy contract is malformed or cannot be safely loaded."""


_active_strategy_indexes: contextvars.ContextVar[tuple[dict[str, Any], ...]] = (
    contextvars.ContextVar("active_strategy_indexes", default=())
)


STRATEGY_EXECUTE_SCHEMA: dict[str, Any] = {
    "name": "strategy_execute",
    "description": (
        "Execute a capability from an explicitly loaded executable skill "
        "strategy. Authority comes only from the trusted current turn."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "capability": {"type": "string"},
            "intent_relation": {
                "type": "string",
                "enum": ["new", "follow_up", "correction"],
            },
            "intent_reference": {"type": "string"},
            "inputs": {"type": "object", "additionalProperties": True},
        },
        "required": ["capability", "intent_relation", "inputs"],
        "additionalProperties": False,
    },
}


def strategy_execute_service_available(*, platform: str | None = None) -> bool:
    """Return whether a new session may expose the fixed strategy interface."""
    from agent.execution_authority import TurnCapability, current_execution_authority

    if current_execution_authority().allows(TurnCapability.CONTRACT_EXECUTE):
        return True
    origin = (platform or "").strip().lower()
    if origin == "tui":
        return True
    return False


def executable_strategies_available() -> bool:
    """Probe compact indexes only; manifests remain lazy until execution."""
    try:
        from agent.skill_utils import get_all_skills_dirs

        return bool(discover_strategy_indexes(get_all_skills_dirs()))
    except Exception:
        return False


def attach_strategy_execute_tool(agent) -> None:
    """Attach the fixed schema once at construction for eligible sessions."""
    tool_name = "strategy_execute"
    agent.tools = [
        tool
        for tool in (getattr(agent, "tools", []) or [])
        if tool.get("function", {}).get("name") != tool_name
    ]
    agent.valid_tool_names = set(getattr(agent, "valid_tool_names", set()) or set())
    agent.valid_tool_names.discard(tool_name)
    static_tools = tuple(
        tool
        for tool in (getattr(agent, "_construction_static_tools", ()) or ())
        if tool.get("function", {}).get("name") != tool_name
    )
    agent._construction_static_tools = static_tools

    if not strategy_execute_service_available(
        platform=getattr(agent, "platform", None),
    ) or not executable_strategies_available():
        return

    wrapped_schema = {"type": "function", "function": STRATEGY_EXECUTE_SCHEMA}
    agent.tools.append(wrapped_schema)
    agent.valid_tool_names.add(tool_name)
    agent._construction_static_tools = (*static_tools, wrapped_schema)


def execute_strategy_for_agent(agent, args: dict[str, Any], *, task_id: str | None = None) -> str:
    """Execute an activated strategy and durably record its structured trace."""
    result = execute_active_strategy(
        capability=str(args.get("capability") or ""),
        inputs=args.get("inputs") if isinstance(args.get("inputs"), dict) else {},
        registry=_AgentContractRegistry(agent, task_id),
        authority_capabilities=current_execution_capabilities(),
    )
    trace = {
        **{key: value for key, value in result.items() if key != "result"},
        "intent_relation": str(args.get("intent_relation") or "new"),
        "intent_reference": args.get("intent_reference"),
    }
    session_db = getattr(agent, "_session_db", None)
    session_id = getattr(agent, "session_id", None)
    trace_persisted = False
    if isinstance(trace, dict) and session_db is not None and session_id:
        try:
            if hasattr(agent, "_ensure_db_session"):
                agent._ensure_db_session()
            session_db.append_strategy_trace(session_id, trace)
            trace_persisted = True
        except Exception:
            logger.warning("Could not persist strategy trace", exc_info=True)
    if result.get("status") == "success" and not trace_persisted:
        return json.dumps(
            {
                **trace,
                "status": "failed",
                "terminal_state": "failed",
                "error_type": "trace_persistence_error",
                "error": (
                    "Contracted operation completed, but its execution trace "
                    "could not be persisted."
                ),
                "operation_completed": True,
            },
            ensure_ascii=False,
        )
    return json.dumps(result, ensure_ascii=False)


def current_execution_capabilities() -> frozenset[Any]:
    """Recompute trusted per-turn capabilities at the dispatch boundary."""
    from agent.execution_authority import current_execution_authority

    return current_execution_authority().capabilities


def _contract_registry():
    from tools.registry import registry

    return registry


class _AgentContractRegistry:
    """Registry view that preserves normal tool policy at provider dispatch."""

    def __init__(self, agent, task_id: str | None):
        self._agent = agent
        self._task_id = task_id
        self._registry = _contract_registry()

    def __getattr__(self, name: str):
        return getattr(self._registry, name)

    def contract_operation_available(self, operation: str) -> bool:
        tool_name = self._registry.get_contract_tool_name(operation)
        allowed_tools = getattr(self._agent, "valid_tool_names", None)
        return bool(
            tool_name
            and (allowed_tools is None or tool_name in allowed_tools)
            and self._registry.contract_operation_available(operation)
        )

    def dispatch_contract_operation(self, operation: str, args: dict) -> str | dict:
        tool_name = self._registry.get_contract_tool_name(operation)
        if not tool_name:
            raise StrategyContractError(
                f"contracted operation {operation!r} has no unambiguous provider tool"
            )
        invoke_tool = getattr(self._agent, "_invoke_tool", None)
        if not callable(invoke_tool):
            raise StrategyContractError("agent policy dispatcher is unavailable")
        raw = invoke_tool(
            tool_name,
            args,
            self._task_id or "",
            tool_call_id=f"strategy:{operation}",
        )
        return self._registry.normalize_contract_result(operation, raw)


def _frontmatter(raw: str) -> dict[str, Any]:
    if not raw.startswith("---"):
        return {}
    end = raw.find("\n---", 3)
    if end < 0:
        return {}
    try:
        loaded = yaml.safe_load(raw[3:end]) or {}
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _strategy_section(frontmatter: Mapping[str, Any]) -> Mapping[str, Any] | None:
    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    hermes = metadata.get("hermes")
    if not isinstance(hermes, Mapping):
        return None
    strategies = hermes.get("strategies")
    return strategies if isinstance(strategies, Mapping) else None


def _compact_indexes(
    *, skill_root: Path, skill_name: str, strategies: Mapping[str, Any]
) -> list[dict[str, Any]]:
    version = strategies.get("version")
    if version != _SUPPORTED_INDEX_VERSION:
        return []
    capabilities = strategies.get("capabilities")
    if not isinstance(capabilities, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in capabilities:
        if not isinstance(raw, Mapping):
            continue
        capability = raw.get("id")
        manifest = raw.get("manifest")
        if (
            not isinstance(capability, str)
            or not _ID_RE.fullmatch(capability)
            or capability in seen
            or not isinstance(manifest, str)
            or not manifest.strip()
        ):
            continue
        seen.add(capability)
        result.append(
            {
                "skill": skill_name,
                "skill_root": str(skill_root.resolve()),
                "index_version": version,
                "capability": capability,
                "manifest": manifest,
            }
        )
    return result


def discover_strategy_indexes(skill_roots: Iterable[Path]) -> list[dict[str, Any]]:
    """Read compact frontmatter indexes without opening strategy manifests."""
    discovered: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for scan_root in skill_roots:
        root = Path(scan_root)
        if not root.exists():
            continue
        for skill_md in iter_skill_index_files(root, "SKILL.md"):
            if any(part in {".git", ".github", ".hub", ".archive"} for part in skill_md.parts):
                continue
            try:
                frontmatter = _frontmatter(skill_md.read_text(encoding="utf-8"))
            except OSError:
                continue
            strategies = _strategy_section(frontmatter)
            if strategies is None:
                continue
            skill_name = frontmatter.get("name") or skill_md.parent.name
            if not isinstance(skill_name, str) or not skill_name.strip():
                continue
            for entry in _compact_indexes(
                skill_root=skill_md.parent,
                skill_name=skill_name.strip(),
                strategies=strategies,
            ):
                key = (entry["skill"], entry["capability"])
                if key in seen:
                    continue
                seen.add(key)
                discovered.append(entry)
    return discovered


def strategy_indexes_from_skill(raw_skill: str, skill_root: Path) -> list[dict[str, Any]]:
    """Extract the activated skill's compact index from already-loaded content."""
    frontmatter = _frontmatter(raw_skill)
    strategies = _strategy_section(frontmatter)
    if strategies is None:
        return []
    skill_name = frontmatter.get("name") or Path(skill_root).name
    if not isinstance(skill_name, str) or not skill_name.strip():
        return []
    return _compact_indexes(
        skill_root=Path(skill_root),
        skill_name=skill_name.strip(),
        strategies=strategies,
    )


def activate_strategy_message(
    message: str, raw_skill: str, skill_root: Path | None
) -> str:
    """Append a compact machine-readable activation index to a skill message."""
    if skill_root is None:
        return message
    indexes = strategy_indexes_from_skill(raw_skill, skill_root)
    if not indexes:
        return message
    canonical = json.dumps(indexes, sort_keys=True, separators=(",", ":"))
    signature = hmac.new(
        _INDEX_SIGNING_KEY, canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    payload = json.dumps(
        {"indexes": indexes, "signature": signature},
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{message}\n\n{STRATEGY_INDEX_START}{payload}{STRATEGY_INDEX_END}"


def indexes_from_message(message: Any) -> list[dict[str, Any]]:
    if not isinstance(message, str):
        return []
    start = message.rfind(STRATEGY_INDEX_START)
    end = message.rfind(STRATEGY_INDEX_END)
    if start < 0 or end <= start:
        return []
    raw = message[start + len(STRATEGY_INDEX_START):end]
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(envelope, dict):
        return []
    indexes = envelope.get("indexes")
    signature = envelope.get("signature")
    if not isinstance(indexes, list):
        return []
    canonical = json.dumps(indexes, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(
        _INDEX_SIGNING_KEY, canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        return []
    return [dict(entry) for entry in indexes if isinstance(entry, dict)]


def set_active_strategies_from_message(message: Any):
    """Bind only strategies explicitly activated by this turn's skill message."""
    return _active_strategy_indexes.set(tuple(indexes_from_message(message)))


def reset_active_strategies(token) -> None:
    _active_strategy_indexes.reset(token)


def active_strategy_indexes() -> tuple[dict[str, Any], ...]:
    return _active_strategy_indexes.get()


def has_active_strategies() -> bool:
    return bool(active_strategy_indexes())


def _contained_file(skill_root: Path, relative_path: str) -> Path:
    root = Path(skill_root).resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise StrategyContractError("strategy manifest resolves outside skill root") from exc
    if candidate.suffix.lower() not in {".yaml", ".yml"}:
        raise StrategyContractError("strategy manifest must be a YAML file")
    if not candidate.is_file():
        raise StrategyContractError("strategy manifest does not exist")
    return candidate


def _reject_executable_data(value: Any, path: str = "manifest") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).strip().lower()
            if key_text in _FORBIDDEN_MANIFEST_KEYS:
                raise StrategyContractError(
                    f"{path}.{key_text} is forbidden in a data-only strategy manifest"
                )
            _reject_executable_data(child, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_executable_data(child, f"{path}[{index}]")


def load_strategy_manifest(skill_root: Path | str, relative_path: str) -> dict[str, Any]:
    """Path-safely lazy-load one immutable data-only strategy snapshot."""
    manifest_path = _contained_file(Path(skill_root), relative_path)
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise StrategyContractError(f"invalid strategy manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise StrategyContractError("strategy manifest root must be an object")
    _reject_executable_data(manifest)
    return deepcopy(manifest)


def _validate_binding(value: Any, *, node: str, field: str) -> None:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return
    if not isinstance(value, Mapping) or len(value) != 1:
        raise StrategyContractError(f"node {node!r} binding {field!r} is invalid")
    source, source_value = next(iter(value.items()))
    if source == "input" and isinstance(source_value, str) and source_value:
        return
    if source == "constant":
        _validate_binding(source_value, node=node, field=field)
        return
    if source == "result" and isinstance(source_value, str) and source_value:
        return
    raise StrategyContractError(f"node {node!r} binding {field!r} is invalid")


def _compile_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != _SUPPORTED_MANIFEST_VERSION:
        raise StrategyContractError("unsupported strategy manifest schema_version")
    capability = manifest.get("capability")
    if not isinstance(capability, str) or not _ID_RE.fullmatch(capability):
        raise StrategyContractError("strategy capability id is invalid")
    start = manifest.get("start")
    nodes = manifest.get("nodes")
    max_steps = manifest.get("max_steps")
    if not isinstance(nodes, Mapping) or not nodes:
        raise StrategyContractError("strategy nodes must be a non-empty object")
    if not isinstance(start, str) or start not in nodes:
        raise StrategyContractError("strategy start node is missing")
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        raise StrategyContractError("strategy max_steps must be a positive integer")

    for node_name, node in nodes.items():
        if not isinstance(node_name, str) or not isinstance(node, Mapping):
            raise StrategyContractError("strategy node names and values must be objects")
        mode = node.get("mode")
        if mode not in {"contracted", "adaptive"}:
            raise StrategyContractError(f"node {node_name!r} has invalid mode")
        if mode == "adaptive":
            continue
        operation = node.get("operation")
        outcomes = node.get("outcomes")
        bindings = node.get("bindings", {})
        if not isinstance(operation, str) or not _ID_RE.fullmatch(operation):
            raise StrategyContractError(f"node {node_name!r} has invalid operation")
        if not isinstance(outcomes, Mapping) or not outcomes:
            raise StrategyContractError(f"node {node_name!r} has no outcomes")
        if not isinstance(bindings, Mapping):
            raise StrategyContractError(f"node {node_name!r} bindings must be an object")
        for field, binding in bindings.items():
            if not isinstance(field, str) or not field:
                raise StrategyContractError(f"node {node_name!r} has invalid binding field")
            _validate_binding(binding, node=node_name, field=field)
        for outcome, target in outcomes.items():
            if not isinstance(outcome, str) or not outcome:
                raise StrategyContractError(f"node {node_name!r} has invalid outcome")
            if not isinstance(target, Mapping) or len(target) != 1:
                raise StrategyContractError(f"node {node_name!r} outcome {outcome!r} is ambiguous")
            if "next" in target and target["next"] not in nodes:
                raise StrategyContractError(
                    f"node {node_name!r} targets missing node {target['next']!r}"
                )
            if "terminal" in target and target["terminal"] not in _TERMINAL_RESULTS:
                raise StrategyContractError(
                    f"node {node_name!r} has invalid terminal result"
                )
            if "handoff" in target and target["handoff"] != "adaptive":
                raise StrategyContractError(
                    f"node {node_name!r} has invalid handoff"
                )
            if not ({"next", "terminal", "handoff"} & set(target)):
                raise StrategyContractError(
                    f"node {node_name!r} outcome {outcome!r} has no transition"
                )
    return deepcopy(dict(manifest))


def _manifest_digest(manifest: Mapping[str, Any]) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_bindings(
    bindings: Mapping[str, Any], inputs: Mapping[str, Any], previous: Mapping[str, Any]
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for field, binding in bindings.items():
        if not isinstance(binding, Mapping):
            resolved[field] = binding
            continue
        source, key = next(iter(binding.items()))
        if source == "constant":
            resolved[field] = key
        elif source == "input":
            if key not in inputs:
                raise StrategyContractError(f"missing normalized input {key!r}")
            resolved[field] = inputs[key]
        elif source == "result":
            if key not in previous:
                raise StrategyContractError(f"missing normalized prior result {key!r}")
            resolved[field] = previous[key]
    return resolved


def _result(
    *, status: str, capability: str, digest: str, steps: list[dict[str, Any]],
    error_type: str | None = None, error: str | None = None,
    max_steps: int | None = None, operation_result: Mapping[str, Any] | None = None,
    execution_mode: str = "contracted", terminal_state: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "execution_mode": execution_mode,
        "terminal_state": terminal_state or status,
        "capability": capability,
        "manifest_digest": digest,
        "steps": steps,
    }
    if max_steps is not None:
        result["budget"] = {
            "max_steps": max_steps,
            "steps_used": len(steps),
        }
    if operation_result is not None:
        result["result"] = dict(operation_result)
    if error_type:
        result["error_type"] = error_type
    if error:
        result["error"] = error
    return result


def execute_active_strategy(
    *, capability: str, inputs: Mapping[str, Any], registry,
    authority_capabilities: frozenset[Any],
) -> dict[str, Any]:
    """Validate and execute the selected active contracted strategy."""
    from agent.execution_authority import TurnCapability

    if TurnCapability.CONTRACT_EXECUTE not in authority_capabilities:
        return _result(
            status="denied",
            capability=capability,
            digest="",
            steps=[],
            error_type="authorization_denied",
            error="current turn lacks Contract Executor authority",
        )
    matches = [
        entry for entry in active_strategy_indexes()
        if entry.get("capability") == capability
    ]
    if not matches:
        return _result(
            status="not_active",
            capability=capability,
            digest="",
            steps=[],
            error_type="strategy_not_active",
            error="capability was not explicitly activated by a loaded skill",
        )
    if len(matches) != 1:
        return _result(
            status="contract_gap",
            capability=capability,
            digest="",
            steps=[],
            error_type="ambiguous_active_strategy",
            error="more than one active skill claims this capability",
        )

    entry = matches[0]
    try:
        manifest = _compile_manifest(
            load_strategy_manifest(entry["skill_root"], entry["manifest"])
        )
        if manifest["capability"] != capability:
            raise StrategyContractError("strategy index and manifest capability differ")
        for node in manifest["nodes"].values():
            if node.get("mode") != "contracted":
                continue
            operation = node["operation"]
            if not registry.has_contract_operation(operation):
                raise StrategyContractError(
                    f"contracted operation {operation!r} is not registered"
                )
            declared = registry.get_contract_outcomes(operation)
            if declared and not set(node["outcomes"]).issubset(declared):
                raise StrategyContractError(
                    f"manifest declares outcomes not supported by operation {operation!r}"
                )
    except (KeyError, TypeError, StrategyContractError) as exc:
        return _result(
            status="contract_gap",
            capability=capability,
            digest="",
            steps=[],
            error_type="invalid_contract",
            error=str(exc),
        )

    digest = _manifest_digest(manifest)
    steps: list[dict[str, Any]] = []
    previous: Mapping[str, Any] = {}
    current = manifest["start"]
    for _ in range(manifest["max_steps"]):
        node = manifest["nodes"][current]
        if node["mode"] == "adaptive":
            return _result(
                status="handoff",
                capability=capability,
                digest=digest,
                steps=steps,
                error_type="adaptive_handoff",
                execution_mode="hybrid" if steps else "adaptive",
            )
        operation = node["operation"]
        if not registry.contract_operation_available(operation):
            return _result(
                status="unavailable",
                capability=capability,
                digest=digest,
                steps=steps,
                error_type="operation_unavailable",
                error=f"contracted operation {operation!r} is unavailable",
            )
        try:
            arguments = _resolve_bindings(node.get("bindings", {}), inputs, previous)
            raw = registry.dispatch_contract_operation(operation, arguments)
            if isinstance(raw, Mapping):
                payload = dict(raw)
            else:
                payload = json.loads(raw)
        except (StrategyContractError, json.JSONDecodeError, TypeError) as exc:
            return _result(
                status="failed",
                capability=capability,
                digest=digest,
                steps=steps,
                error_type="provider_contract_error",
                error=str(exc),
            )
        if not isinstance(payload, dict) or not isinstance(payload.get("outcome"), str):
            return _result(
                status="failed",
                capability=capability,
                digest=digest,
                steps=steps,
                error_type="provider_contract_error",
                error="provider operation did not return a normalized outcome",
            )
        outcome = payload["outcome"]
        transition = node["outcomes"].get(outcome)
        if transition is None:
            steps.append(
                {
                    "node": current,
                    "operation": operation,
                    "outcome": outcome,
                    "transition": "contract_gap",
                }
            )
            return _result(
                status="contract_gap",
                capability=capability,
                digest=digest,
                steps=steps,
                error_type="unknown_normalized_outcome",
                error=f"outcome {outcome!r} has no legal transition",
            )
        if "next" in transition:
            transition_text = f"next:{transition['next']}"
        elif "terminal" in transition:
            transition_text = f"terminal:{transition['terminal']}"
        else:
            transition_text = "handoff:adaptive"
        steps.append(
            {
                "node": current,
                "operation": operation,
                "outcome": outcome,
                "transition": transition_text,
            }
        )
        previous = payload
        if "terminal" in transition:
            return _result(
                status=transition["terminal"],
                capability=capability,
                digest=digest,
                steps=steps,
                max_steps=manifest["max_steps"],
                operation_result=payload,
            )
        if "handoff" in transition:
            return _result(
                status="handoff",
                capability=capability,
                digest=digest,
                steps=steps,
                error_type="adaptive_handoff",
                max_steps=manifest["max_steps"],
                execution_mode="hybrid",
            )
        current = transition["next"]

    return _result(
        status="budget_exhausted",
        capability=capability,
        digest=digest,
        steps=steps,
        error_type="step_budget_exhausted",
        max_steps=manifest["max_steps"],
    )

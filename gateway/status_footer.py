"""Gateway message status footer formatting.

This module is intentionally small and pure: gateway callers pass the completed
agent result plus user config, and receive either the original response or a
response with a compact status footer appended.
"""

from __future__ import annotations

from typing import Any, Mapping


def _short_session_id(session_id: Any) -> str:
    value = str(session_id or "").strip()
    if not value:
        return ""
    # Keep the footer compact while preserving the most distinctive suffix for
    # timestamp/UUID-like ids.
    return value[-6:]


def _count_tool_calls(result: Mapping[str, Any]) -> int:
    """Best-effort count of actual tool invocations in an agent result."""
    try:
        explicit = result.get("tool_call_count")
        if explicit is not None:
            return max(0, int(explicit or 0))
    except Exception:
        pass

    count = 0
    messages = result.get("messages") or []
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, Mapping):
                continue
            role = msg.get("role")
            if role in ("tool", "function"):
                count += 1
                continue
            calls = msg.get("tool_calls")
            if isinstance(calls, list):
                count += len(calls)
    return count


def _platform_value(platform: Any) -> str:
    return getattr(platform, "value", str(platform or "")).lower()


def _format_k(tokens: Any) -> str:
    try:
        value = int(tokens or 0)
    except Exception:
        value = 0
    if value >= 1000:
        return f"{value // 1000}K"
    return str(value)


def _footer_config(config: Mapping[str, Any] | None) -> Mapping[str, Any]:
    display = (config or {}).get("display", {}) if isinstance(config, Mapping) else {}
    if not isinstance(display, Mapping):
        return {}
    footer = display.get("message_status_footer", {})
    return footer if isinstance(footer, Mapping) else {}


def is_status_footer_enabled(config: Mapping[str, Any] | None, platform: Any) -> bool:
    """Return True when the message footer is enabled for *platform*."""
    footer = _footer_config(config)
    if not footer.get("enabled", False):
        return False

    platforms = footer.get("platforms")
    if not platforms:
        return True
    if isinstance(platforms, str):
        platforms = [platforms]

    platform_name = _platform_value(platform)
    allowed = {str(p).lower() for p in platforms}
    return platform_name in allowed


def build_status_footer(agent_result: Mapping[str, Any] | None, response_time: float | None = None) -> str:
    """Build the compact status footer from an agent result dict."""
    result = agent_result or {}
    model = result.get("model") or "unknown"
    provider = result.get("provider") or ""
    if provider == "custom":
        provider = result.get("config_provider") or provider
    profile = result.get("profile") or result.get("profile_name") or ""
    session_short = _short_session_id(result.get("session_id"))
    tool_calls = _count_tool_calls(result)
    reasoning_effort = str(result.get("reasoning_effort") or "").strip().lower()
    if not reasoning_effort:
        reasoning_config = result.get("reasoning_config") or {}
        if isinstance(reasoning_config, Mapping):
            if reasoning_config.get("enabled") is False:
                reasoning_effort = "off"
            else:
                reasoning_effort = str(reasoning_config.get("effort") or "").strip().lower()

    try:
        used = int(result.get("last_prompt_tokens") or 0)
    except Exception:
        used = 0
    try:
        total = int(result.get("context_length") or 0)
    except Exception:
        total = 0

    pct = 0
    if total > 0:
        pct = max(0, min(100, round((used / total) * 100)))

    try:
        compressions = int(result.get("compression_count") or result.get("compressions") or 0)
    except Exception:
        compressions = 0

    try:
        api_calls = int(result.get("api_calls") or 0)
    except Exception:
        api_calls = 0

    try:
        input_t = int(result.get("input_tokens") or 0)
    except Exception:
        input_t = 0
    try:
        output_t = int(result.get("output_tokens") or 0)
    except Exception:
        output_t = 0

    try:
        cost = float(result.get("estimated_cost_usd") or 0)
    except Exception:
        cost = 0.0

    if total > 0:
        context = f"{pct}% {_format_k(used)}/{_format_k(total)}"
    else:
        context = "n/a"

    parts = []
    if profile:
        parts.append(f"🧩 {profile}")
    model_part = f"🧠 {model}"
    if provider:
        model_part += f"/{provider}"
    parts.extend([
        model_part,
        f"💭 {reasoning_effort}" if reasoning_effort else "",
        f"📏 {context}",
        f"🔁 {api_calls}次",
        f"🔧 {tool_calls}",
    ])
    parts = [p for p in parts if p]
    if input_t or output_t:
        parts.append(f"📦 入{_format_k(input_t)}/出{_format_k(output_t)}")
    if response_time is not None and response_time > 0:
        parts.append(f"🕒 {response_time:.1f}s")
    if cost > 0:
        parts.append(f"💰 ${cost:.4f}")
    if session_short:
        parts.append(f"🧵 {session_short}")
    parts.append(f"🗜️ {compressions}")

    return " | ".join(parts)


def append_status_footer(
    response: str,
    agent_result: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
    platform: Any,
    response_time: float | None = None,
) -> str:
    """Append a compact status footer to *response* when enabled."""
    if not response or not is_status_footer_enabled(config, platform):
        return response
    return f"{response.rstrip()}\n\n——\n{build_status_footer(agent_result, response_time=response_time)}"

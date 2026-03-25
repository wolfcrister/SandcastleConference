"""Agent Factory — builds autogen agents dynamically from persona definitions."""

from __future__ import annotations

import autogen
from tools import TOOL_MAP

_DEFAULT_MODEL = "gpt-4o"
_DEFAULT_TEMPERATURE = 0.7


def _llm_config(persona: dict) -> dict:
    """Build the llm_config dict for a single persona."""
    return {
        "config_list": [
            {
                "model": persona.get("model", _DEFAULT_MODEL),
                "temperature": persona.get("temperature", _DEFAULT_TEMPERATURE),
            }
        ],
    }


def build_agent(persona: dict) -> autogen.AssistantAgent:
    """Create an AssistantAgent from a persona dict.

    Tool functions listed in persona["tools"] are registered on the agent
    so that the LLM can call them during conversation.
    """
    agent = autogen.AssistantAgent(
        name=persona["name"].replace(" ", "_"),
        system_message=persona["system_prompt"],
        llm_config=_llm_config(persona),
    )
    # Register each tool the persona is allowed to use
    for tool_name in persona.get("tools", []):
        fn = TOOL_MAP.get(tool_name)
        if fn is None:
            raise ValueError(
                f"Persona {persona['name']!r} references unknown tool: {tool_name!r}"
            )
        agent.register_for_llm(description=fn.__doc__)(fn)
    return agent


def build_director() -> autogen.UserProxyAgent:
    """Create the human-in-the-loop Director (Chairman) agent.

    human_input_mode=ALWAYS ensures no agent acts without the Director's
    explicit trigger.  Code execution is disabled for safety.
    """
    director = autogen.UserProxyAgent(
        name="Director",
        human_input_mode="ALWAYS",
        code_execution_config=False,
    )
    # Register tools on the Director so it can execute them on behalf of agents
    for fn in TOOL_MAP.values():
        director.register_for_execution()(fn)
    return director

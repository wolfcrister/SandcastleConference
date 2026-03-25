"""Sandcastle Conference — main Chainlit application.

Launch with:  chainlit run app.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

import autogen
import chainlit as cl
from chainlit.input_widget import Slider, Switch

import base64

import tools
from registry import PersonaRegistry
from factory import build_agent, build_director
from session_manager import SessionManager

# ---------------------------------------------------------------------------
# Boot: environment
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env")

_api_key = os.getenv("SANDCASTLE_CONFERENCE_KEY")
_project_path = os.getenv("GAME_PROJECT_PATH")

_sm = SessionManager()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _persona_display(p: dict) -> str:
    return f"{p['avatar']}  {p['name']} — {p['role']}"


def _emoji_avatar_url(emoji: str) -> str:
    """Convert an emoji character to a data-URI SVG for use as a Chainlit avatar."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
        f'<text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-size="48">{emoji}</text>'
        '</svg>'
    )
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


async def _run_group_round(user_msg: str) -> None:
    """Director sends a message; each active agent replies, repeated for N rounds."""
    session = cl.user_session.get("session")
    groupchat: autogen.GroupChat = cl.user_session.get("groupchat")
    agents: list[autogen.AssistantAgent] = cl.user_session.get("agents")
    personas_map: dict[str, dict] = cl.user_session.get("personas_map")
    agent_enabled: dict[str, bool] = cl.user_session.get("agent_enabled", {})
    rounds = int(cl.user_session.get("rounds", 1))

    # Record Director message in GroupChat history
    director_msg = {"role": "user", "name": "Director", "content": user_msg}
    groupchat.messages.append(director_msg)
    _sm.append_message(session, role="user", name="Director", content=user_msg)

    for round_num in range(rounds):
        if rounds > 1:
            await cl.Message(content=f"--- **Round {round_num + 1} / {rounds}** ---").send()

        # Each active agent generates a reply
        for agent in agents:
            # Skip disabled agents
            if not agent_enabled.get(agent.name, True):
                continue

            persona = personas_map.get(agent.name, {})

            # Show thinking indicator
            thinking_msg = cl.Message(author=agent.name, content="")
            await thinking_msg.send()

            # Build the messages list the agent sees
            agent_messages = [{"role": "system", "content": agent.system_message}]
            for m in groupchat.messages:
                if m["name"] == agent.name:
                    agent_messages.append({"role": "assistant", "content": m["content"]})
                else:
                    agent_messages.append({"role": "user", "name": m["name"], "content": m["content"]})

            # Call the LLM
            try:
                response = await asyncio.to_thread(
                    agent.client.create,
                    messages=agent_messages,
                )
                reply = response.choices[0].message.content or ""
            except Exception as exc:
                reply = f"⚠️ Error generating response: {exc}"

            # Record in GroupChat history
            groupchat.messages.append({"role": "assistant", "name": agent.name, "content": reply})
            _sm.append_message(session, role="assistant", name=agent.name, content=reply)

            # Update the thinking message with the actual reply
            thinking_msg.content = reply
            thinking_msg.author = agent.name
            await thinking_msg.update()


# ---------------------------------------------------------------------------
# Chainlit lifecycle
# ---------------------------------------------------------------------------

@cl.on_chat_start
async def on_chat_start():
    # --- validate config ---------------------------------------------------
    if not _api_key:
        await cl.Message(
            content="⚠️ **Missing API Key.** Set `SANDCASTLE_CONFERENCE_KEY` in your `.env` file and restart."
        ).send()
        return
    os.environ["OPENAI_API_KEY"] = _api_key

    if not _project_path or not os.path.isdir(_project_path):
        await cl.Message(
            content="⚠️ **Invalid GAME_PROJECT_PATH.** Set a valid directory path in `.env` and restart."
        ).send()
        return
    tools.configure(_project_path)

    # --- load persona registry ---------------------------------------------
    try:
        registry = PersonaRegistry()
    except Exception as exc:
        await cl.Message(content=f"⚠️ **Failed to load personas.json:** {exc}").send()
        return

    # --- check for saved sessions to resume --------------------------------
    previous = _sm.list_sessions()
    resume_session = None

    if previous:
        actions = [
            cl.Action(name="new_session", payload={"value": "new"}, label="🆕 New Session"),
        ]
        for s in previous[:10]:
            actions.append(cl.Action(name="resume_session", payload={"value": s}, label=f"📂 {s}"))

        res = await cl.AskActionMessage(
            content="**Welcome, Director.** Start a new session or resume a previous one?",
            actions=actions,
        ).send()

        if res and res.get("payload", {}).get("value") != "new":
            resume_session = res["payload"]["value"]

    # --- session name ------------------------------------------------------
    if resume_session:
        session_data = _sm.load(resume_session)
        session_name = session_data["name"]
        participant_names = session_data["participants"]
        await cl.Message(content=f"📂 Resuming session **{session_name}** with {len(session_data['messages'])} messages of context.").send()

        # Replay history for context
        for msg in session_data["messages"]:
            persona = {p["name"]: p for p in registry.all()}.get(msg["name"], {})
            avatar = persona.get("avatar", "👤" if msg["role"] == "user" else "🤖")
            await cl.Message(author=msg["name"], content=msg["content"]).send()
    else:
        res = await cl.AskUserMessage(
            content="**Welcome, Director.** Name this session (e.g. `Combat_Refactor_V1`):",
            timeout=300,
        ).send()
        if not res:
            return
        session_name = res["output"].strip()
        participant_names = None

    # --- cast agents -------------------------------------------------------
    all_personas = registry.all()

    if participant_names:
        # Resuming — rebuild the same cast
        selected_names = participant_names
    else:
        # New session — let Director pick
        actions = [
            cl.Action(
                name=p["name"],
                payload={"value": p["name"]},
                label=_persona_display(p),
            )
            for p in all_personas
        ]
        res = await cl.AskActionMessage(
            content="**Select agents to summon** (pick one at a time, then type `done`).\n\nAvailable:\n"
            + "\n".join(f"- {_persona_display(p)}" for p in all_personas),
            actions=actions,
        ).send()

        # Collect selected agents (simple: pick via actions until user types done)
        selected_names = []
        if res:
            selected_names.append(res["payload"]["value"])

        # For v1, ask explicitly for more
        while True:
            remaining = [p for p in all_personas if p["name"] not in selected_names]
            if not remaining:
                break
            actions = [
                cl.Action(
                    name=p["name"],
                    payload={"value": p["name"]},
                    label=_persona_display(p),
                )
                for p in remaining
            ]
            actions.append(cl.Action(name="done", payload={"value": "done"}, label="✅ Done — Start Session"))
            res = await cl.AskActionMessage(
                content=f"**Selected so far:** {', '.join(selected_names)}\n\nAdd another agent or start the session:",
                actions=actions,
            ).send()
            if not res or res["payload"]["value"] == "done":
                break
            selected_names.append(res["payload"]["value"])

    if not selected_names:
        await cl.Message(content="No agents selected. Session cancelled.").send()
        return

    # --- build autogen agents ----------------------------------------------
    agents = []
    personas_map: dict[str, dict] = {}

    for name in selected_names:
        persona = registry.get(name)
        agent = build_agent(persona)
        agents.append(agent)
        personas_map[agent.name] = persona

    groupchat = autogen.GroupChat(
        agents=agents,
        messages=[],
        max_round=50,
        speaker_selection_method="round_robin",
    )

    # If resuming, seed the groupchat with history
    if resume_session:
        for msg in session_data["messages"]:
            groupchat.messages.append({
                "role": msg["role"],
                "name": msg["name"],
                "content": msg["content"],
            })

    # --- create / restore session state ------------------------------------
    if resume_session:
        session = session_data
    else:
        session = _sm.create(session_name, selected_names)

    # Store everything in Chainlit user session
    cl.user_session.set("session", session)
    cl.user_session.set("agents", agents)
    cl.user_session.set("groupchat", groupchat)
    cl.user_session.set("personas_map", personas_map)
    cl.user_session.set("registry", registry)
    cl.user_session.set("rounds", 1)

    # Default: all agents enabled
    agent_enabled = {a.name: True for a in agents}
    cl.user_session.set("agent_enabled", agent_enabled)

    # Register avatars for each agent
    for agent in agents:
        persona = personas_map[agent.name]
        await cl.Avatar(name=agent.name, url=_emoji_avatar_url(persona["avatar"])).send()

    # --- settings panel ----------------------------------------------------
    settings_widgets = [
        Slider(
            id="rounds",
            label="Response rounds per message",
            initial=1,
            min=1,
            max=5,
            step=1,
            description="How many times each agent responds per Director message",
        ),
    ]
    # Add a toggle for each agent
    for agent in agents:
        persona = personas_map[agent.name]
        settings_widgets.append(
            Switch(
                id=f"agent_{agent.name}",
                label=f"{persona['avatar']}  {persona['name']}",
                initial=True,
                description=f"Enable/disable {persona['name']} in the conversation",
            )
        )
    settings = cl.ChatSettings(settings_widgets)
    await settings.send()

    cast_list = "\n".join(f"- {personas_map[a.name]['avatar']}  **{personas_map[a.name]['name']}** — {personas_map[a.name]['role']}" for a in agents)
    await cl.Message(
        content=f"🏖️ **Session: {session_name}**\n\n**The room is ready, Director. Your cast:**\n{cast_list}\n\nType your opening topic to begin.",
        actions=[cl.Action(name="call_the_vote", payload={"value": "vote"}, label="🗳️ Call The Vote")],
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    text = message.content.strip()

    # ---- Persona management commands (available even without a session) ----
    if text.lower() == "/personas":
        await _cmd_personas()
        return
    if text.lower().startswith("/addpersona"):
        await _cmd_addpersona()
        return
    if text.lower().startswith("/editpersona"):
        arg = text[len("/editpersona"):].strip()
        await _cmd_editpersona(arg)
        return
    if text.lower().startswith("/delpersona"):
        arg = text[len("/delpersona"):].strip()
        await _cmd_delpersona(arg)
        return
    if text.lower() == "/help":
        await cl.Message(content=(
            "**Available commands:**\n"
            "- `/personas` — list all personas\n"
            "- `/addpersona` — create a new persona (interactive)\n"
            "- `/editpersona <name>` — edit fields of an existing persona\n"
            "- `/delpersona <name>` — delete a persona\n"
            "- `/help` — show this message"
        )).send()
        return

    # ---- Normal message: requires an active session -----------------------
    if not cl.user_session.get("agents"):
        await cl.Message(content="⚠️ No active session. Please restart.").send()
        return
    await _run_group_round(text)


# ---------------------------------------------------------------------------
# Persona management commands
# ---------------------------------------------------------------------------

async def _cmd_personas():
    """List all personas from the registry."""
    registry = PersonaRegistry()
    personas = registry.all()
    if not personas:
        await cl.Message(content="No personas defined yet. Use `/addpersona` to create one.").send()
        return
    lines = [f"{p['avatar']}  **{p['name']}** — {p['role']}" for p in personas]
    await cl.Message(content="**Registered Personas:**\n" + "\n".join(f"- {l}" for l in lines)).send()


async def _cmd_addpersona():
    """Interactive flow to create a new persona."""
    res = await cl.AskUserMessage(content="**New Persona — Name:** (e.g. `Level Designer`)", timeout=120).send()
    if not res:
        return
    name = res["output"].strip()

    res = await cl.AskUserMessage(content="**Avatar emoji:** (e.g. `🗺️`)", timeout=120).send()
    if not res:
        return
    avatar = res["output"].strip()

    res = await cl.AskUserMessage(content="**Role** (short description):", timeout=120).send()
    if not res:
        return
    role = res["output"].strip()

    res = await cl.AskUserMessage(content="**System prompt** (the agent's personality & instructions):", timeout=300).send()
    if not res:
        return
    system_prompt = res["output"].strip()

    res = await cl.AskUserMessage(content="**Tools** — comma-separated list or `none`:\nAvailable: `list_dir`, `read_file`", timeout=120).send()
    if not res:
        return
    tools_raw = res["output"].strip()
    tool_list = [] if tools_raw.lower() == "none" else [t.strip() for t in tools_raw.split(",") if t.strip()]

    persona = {
        "name": name,
        "avatar": avatar,
        "role": role,
        "system_prompt": system_prompt,
        "tools": tool_list,
        "model": "gpt-4o",
        "temperature": 0.7,
    }

    try:
        registry = PersonaRegistry()
        registry.add(persona)
        await cl.Message(content=f"✅ Persona **{name}** created! Restart the session to use it.").send()
    except ValueError as exc:
        await cl.Message(content=f"⚠️ Could not add persona: {exc}").send()


async def _cmd_editpersona(name: str):
    """Edit an existing persona's fields."""
    if not name:
        await cl.Message(content="Usage: `/editpersona <name>`").send()
        return

    registry = PersonaRegistry()
    try:
        persona = registry.get(name)
    except KeyError:
        await cl.Message(content=f"⚠️ Persona **{name}** not found. Use `/personas` to list available ones.").send()
        return

    # Show current values
    current = (
        f"**Editing: {persona['name']}**\n"
        f"- **avatar:** {persona['avatar']}\n"
        f"- **role:** {persona['role']}\n"
        f"- **system_prompt:** {persona['system_prompt'][:120]}{'…' if len(persona.get('system_prompt','')) > 120 else ''}\n"
        f"- **tools:** {', '.join(persona.get('tools', [])) or 'none'}\n"
        f"- **model:** {persona.get('model', 'gpt-4o')}\n"
        f"- **temperature:** {persona.get('temperature', 0.7)}\n\n"
        "Which field to edit? (or `done` to finish)"
    )
    await cl.Message(content=current).send()

    editable = {"avatar", "role", "system_prompt", "tools", "model", "temperature"}
    updates: dict = {}

    while True:
        res = await cl.AskUserMessage(content="Field name (or `done`):", timeout=120).send()
        if not res:
            break
        field = res["output"].strip().lower()
        if field == "done":
            break
        if field not in editable:
            await cl.Message(content=f"Unknown field. Choose from: {', '.join(sorted(editable))}").send()
            continue

        res = await cl.AskUserMessage(content=f"New value for **{field}**:", timeout=300).send()
        if not res:
            break
        value = res["output"].strip()

        if field == "tools":
            value = [] if value.lower() == "none" else [t.strip() for t in value.split(",") if t.strip()]
        elif field == "temperature":
            try:
                value = float(value)
            except ValueError:
                await cl.Message(content="Temperature must be a number.").send()
                continue

        updates[field] = value

    if updates:
        try:
            registry.update(name, updates)
            await cl.Message(content=f"✅ Persona **{name}** updated! Restart the session to apply changes.").send()
        except ValueError as exc:
            await cl.Message(content=f"⚠️ Could not update: {exc}").send()
    else:
        await cl.Message(content="No changes made.").send()


async def _cmd_delpersona(name: str):
    """Delete a persona after confirmation."""
    if not name:
        await cl.Message(content="Usage: `/delpersona <name>`").send()
        return

    registry = PersonaRegistry()
    try:
        registry.get(name)
    except KeyError:
        await cl.Message(content=f"⚠️ Persona **{name}** not found.").send()
        return

    res = await cl.AskActionMessage(
        content=f"Are you sure you want to delete **{name}**? This cannot be undone.",
        actions=[
            cl.Action(name="confirm", payload={"value": "yes"}, label="🗑️ Delete"),
            cl.Action(name="cancel", payload={"value": "no"}, label="Cancel"),
        ],
    ).send()

    if res and res.get("payload", {}).get("value") == "yes":
        registry.delete(name)
        await cl.Message(content=f"✅ Persona **{name}** deleted.").send()
    else:
        await cl.Message(content="Cancelled.").send()


# ---------------------------------------------------------------------------
# Settings update
# ---------------------------------------------------------------------------

@cl.on_settings_update
async def on_settings_update(settings: dict):
    """Handle changes from the settings panel."""
    agents = cl.user_session.get("agents", [])
    personas_map = cl.user_session.get("personas_map", {})

    # Update rounds
    if "rounds" in settings:
        cl.user_session.set("rounds", int(settings["rounds"]))

    # Update agent toggles
    agent_enabled = cl.user_session.get("agent_enabled", {})
    changes = []
    for agent in agents:
        key = f"agent_{agent.name}"
        if key in settings:
            was_enabled = agent_enabled.get(agent.name, True)
            now_enabled = bool(settings[key])
            agent_enabled[agent.name] = now_enabled
            if was_enabled != now_enabled:
                persona = personas_map.get(agent.name, {})
                status = "joined" if now_enabled else "left"
                changes.append(f"{persona.get('avatar', '🤖')} **{persona.get('name', agent.name)}** {status} the room")
    cl.user_session.set("agent_enabled", agent_enabled)

    # Announce changes
    rounds = int(cl.user_session.get("rounds", 1))
    active_count = sum(1 for v in agent_enabled.values() if v)
    summary = f"⚙️ **Settings updated** — {active_count} agents active, {rounds} round(s) per message"
    if changes:
        summary += "\n" + "\n".join(f"- {c}" for c in changes)
    await cl.Message(content=summary).send()


# ---------------------------------------------------------------------------
# Action: The Vote
# ---------------------------------------------------------------------------

@cl.action_callback("call_the_vote")
async def on_vote(action: cl.Action):
    await _run_group_round(
        "ALL AGENTS: Provide your Final Verdict on the current topic. "
        "Format: **[YES / NO / CONDITIONAL]** — one-sentence rationale."
    )

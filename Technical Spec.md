# Technical Specification: Sandcastle Conference (v3.0)

## 1. Project Vision
**Sandcastle Conference** is a dynamic, multi-agent "War Room" for game development. The **Game Director (Human/Chairman)** "summons" specific AI experts (Personas) into a virtual conference to debate features, inspect local source code, and provide project estimates. 

### Core Philosophy: **Zero Hardcoding.**
All personas, tools, and session data must be managed via external registries (JSON/DB) and environment variables. Hardcoding is considered a failure in architectural design.

---

## 2. Technical Stack & Environment
* **Orchestration:** `pyautogen` (Multi-agent GroupChat logic).
* **UI Framework:** `chainlit` (Web interface with action buttons and sidebar).
* **Language:** Python 3.10+.
* **API Configuration:**
    * API Key Name: **SANDCASTLE_CONFERENCE_KEY** (Must be read from `.env`).
    * Project Path: **GAME_PROJECT_PATH** (Local path to game source code, read from `.env`).

---

## 3. The Persona Registry (personas.json)
The application must load all agent definitions from an external `personas.json` file. 

**Required Fields per Persona:**
* `name`: Unique identifier.
* `avatar`: Emoji or icon string.
* `role`: Professional title.
* `system_prompt`: The instructions defining their personality and goals.
* `tools`: A list of strings (e.g., ["file_read", "list_dir"]) mapping to Python functions.

* **UI Requirement:** The Director must be able to Create, Edit, and Delete these personas directly from the web interface, which updates the JSON file.

---

## 4. Session Management & Persistence
* **Session Naming:** Upon launch, the Director must name the session (e.g., "Combat_Refactor_V1").
* **Persistence:** Save all chat history, tool outputs, and participant lists to `/sessions/{session_name}.json`.
* **Resume Capability:** The sidebar must list previous sessions. Selecting one reloads the full context and agents into the room.

---

## 5. Interaction Logic (The "Chairman" Pattern)
* **The Gavel:** Set `UserProxyAgent` to `human_input_mode="ALWAYS"`. No agent speaks without the Director's trigger.
* **Casting:** Before the meeting starts, the UI presents a checklist of agents from the Registry. Only selected agents are initialized.
* **Mid-Session Summoning:** Implement a `/summon [Persona_Name]` command. This must:
    1. Initialize the new agent from the Registry.
    2. Inject them into the active GroupChat.
    3. Provide them with the current conversation history.
* **The Vote:** An "Action Button" in the UI that forces all active agents to provide a concise "Final Verdict" (Yes/No/Conditional) on the current topic.

---

## 6. Local Tooling (Method A: Direct Access)
The system must define a tool-wrapper that maps JSON strings to Python functions:
1.  **list_dir**: Returns the file tree of `GAME_PROJECT_PATH`.
2.  **read_file**: Returns the text content of a specific file path within the project.
* **Safety:** Access is Read-Only. Paths must be validated to stay within `GAME_PROJECT_PATH` to prevent directory traversal.

---

## 7. Implementation Instructions for Coding Agent
1.  **Bootloader:** Read `.env` for `SANDCASTLE_CONFERENCE_KEY`. If missing, display a "Missing API Key" error in the Chainlit UI.
2.  **Registry Handler:** Write a class to handle CRUD operations for `personas.json`.
3.  **Agent Factory:** Create a function that builds `autogen.AssistantAgent` objects dynamically based on the JSON definitions, mapping tool names to actual Python functions.
4.  **Chainlit Wrapper:**
    * Use `@cl.on_chat_start` for naming the session and "Casting" the agents.
    * Use `@cl.on_message` to pipe Director input into the AutoGen loop.
    * Ensure "Agent is thinking..." and "Tool call results" are displayed as nested elements in the UI.

---

## 8. Directory Structure
* **/sandcastle-conference**
    * `app.py` (Main Orchestration Logic)
    * `personas.json` (The Talent Registry)
    * `requirements.txt` (pyautogen, chainlit, python-dotenv)
    * `.env` (SANDCASTLE_CONFERENCE_KEY & GAME_PROJECT_PATH)
    * **/sessions** (Saved JSON session logs)
    * **/docs** (Local reference docs)
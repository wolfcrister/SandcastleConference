"""Sandboxed file-system tools for agents.

All paths are validated to stay within GAME_PROJECT_PATH to prevent
directory traversal. Access is strictly read-only.
"""

import os
from pathlib import Path
from typing import Annotated

_MAX_READ_CHARS = 4_000
_MAX_TREE_CHARS = 4_000

# Resolved at import-time by config loader; set via configure().
_project_root: Path | None = None


def configure(project_path: str) -> None:
    """Set the project root that all tool paths are resolved against."""
    global _project_root
    _project_root = Path(project_path).resolve()
    if not _project_root.is_dir():
        raise ValueError(f"GAME_PROJECT_PATH is not a valid directory: {_project_root}")


def _safe_resolve(rel_path: str) -> Path:
    """Resolve *rel_path* inside the project root, rejecting traversal."""
    if _project_root is None:
        raise RuntimeError("Tools not configured — call tools.configure() first.")
    target = (_project_root / rel_path).resolve()
    if not str(target).startswith(str(_project_root)):
        raise PermissionError(f"Access denied — path is outside the project: {rel_path}")
    return target


# -- public tool functions ---------------------------------------------------

def list_dir(
    path: Annotated[str, "Relative path inside the game project (use '.' for root)."] = "."
) -> str:
    """List the file tree of a directory inside the game project."""
    target = _safe_resolve(path)
    if not target.is_dir():
        return f"Error: '{path}' is not a directory."

    lines: list[str] = []
    for root, dirs, files in os.walk(target):
        level = len(Path(root).relative_to(target).parts)
        indent = "  " * level
        lines.append(f"{indent}{Path(root).name}/")
        sub_indent = "  " * (level + 1)
        for f in sorted(files):
            lines.append(f"{sub_indent}{f}")
        # Limit depth to avoid enormous output
        if level >= 2:
            dirs.clear()
    output = "\n".join(lines) if lines else "(empty directory)"
    if len(output) > _MAX_TREE_CHARS:
        output = output[:_MAX_TREE_CHARS] + f"\n\n... [truncated — tree is {len(output)} chars total]"
    return output


def read_file(
    path: Annotated[str, "Relative path to a file inside the game project."]
) -> str:
    """Read the text content of a file inside the game project (capped at ~10 000 chars)."""
    target = _safe_resolve(path)
    if not target.is_file():
        return f"Error: '{path}' is not a file."
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading file: {exc}"
    if len(text) > _MAX_READ_CHARS:
        return text[:_MAX_READ_CHARS] + f"\n\n... [truncated — file is {len(text)} chars total]"
    return text


# Map used by the agent factory to resolve tool name strings from personas.json
TOOL_MAP: dict[str, callable] = {
    "list_dir": list_dir,
    "read_file": read_file,
}

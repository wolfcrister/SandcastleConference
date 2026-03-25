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
    """Read the full text content of a file (capped at ~4000 chars). Prefer read_lines for large files."""
    target = _safe_resolve(path)
    if not target.is_file():
        return f"Error: '{path}' is not a file."
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading file: {exc}"
    if len(text) > _MAX_READ_CHARS:
        return text[:_MAX_READ_CHARS] + f"\n\n... [truncated — file is {len(text)} chars, {len(text.splitlines())} lines total. Use read_lines to read specific sections.]"
    return text


def read_lines(
    path: Annotated[str, "Relative path to a file inside the game project."],
    start: Annotated[int, "Start line number (1-based)."] = 1,
    end: Annotated[int, "End line number (1-based, inclusive)."] = 50,
) -> str:
    """Read specific lines from a file (1-based, inclusive). Use this for targeted reads of large files."""
    target = _safe_resolve(path)
    if not target.is_file():
        return f"Error: '{path}' is not a file."
    try:
        all_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return f"Error reading file: {exc}"
    total = len(all_lines)
    start = max(1, start)
    end = min(end, total)
    if start > total:
        return f"Error: file only has {total} lines."
    selected = all_lines[start - 1 : end]
    header = f"[{path} lines {start}-{end} of {total}]\n"
    return header + "\n".join(f"{i}: {line}" for i, line in enumerate(selected, start=start))


def search_file(
    pattern: Annotated[str, "Text or keyword to search for (case-insensitive)."],
    path: Annotated[str, "Relative path to a file, or '.' to search all files."] = ".",
) -> str:
    """Search for a text pattern in files. Returns matching lines with file paths and line numbers."""
    target = _safe_resolve(path)
    results: list[str] = []
    max_results = 30
    pattern_lower = pattern.lower()

    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = []
        for root, dirs, fnames in os.walk(target):
            level = len(Path(root).relative_to(target).parts)
            if level >= 3:
                dirs.clear()
                continue
            for f in fnames:
                fp = Path(root) / f
                if fp.suffix in {".py", ".gd", ".json", ".cfg", ".md", ".txt", ".tscn", ".tres", ".cs", ".toml", ".yaml", ".yml", ".ini", ".sh", ".bat", ".ps1"}:
                    files.append(fp)
    else:
        return f"Error: '{path}' not found."

    for fp in files:
        if len(results) >= max_results:
            break
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        rel = fp.relative_to(_project_root)
        for i, line in enumerate(lines, 1):
            if pattern_lower in line.lower():
                results.append(f"{rel}:{i}: {line.rstrip()}")
                if len(results) >= max_results:
                    break

    if not results:
        return f"No matches for '{pattern}'."
    output = "\n".join(results)
    if len(results) >= max_results:
        output += f"\n\n... [showing first {max_results} matches]"
    return output


# Map used by the agent factory to resolve tool name strings from personas.json
TOOL_MAP: dict[str, callable] = {
    "list_dir": list_dir,
    "read_file": read_file,
    "read_lines": read_lines,
    "search_file": search_file,
}

"""Session Manager — save, load, and list conference sessions."""

import json
from datetime import datetime, timezone
from pathlib import Path

_SESSIONS_DIR = Path(__file__).parent / "sessions"


class SessionManager:
    """Handles persistence of conference sessions to JSON files."""

    def __init__(self, sessions_dir: Path | None = None):
        self._dir = sessions_dir or _SESSIONS_DIR
        self._dir.mkdir(exist_ok=True)

    # -- public API ----------------------------------------------------------

    def create(self, name: str, participants: list[str]) -> dict:
        """Initialise a new session metadata dict."""
        return {
            "name": name,
            "created": datetime.now(timezone.utc).isoformat(),
            "participants": participants,
            "messages": [],
        }

    def save(self, session: dict) -> Path:
        """Write session state (including messages) to disk."""
        path = self._path_for(session["name"])
        path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, name: str) -> dict:
        """Load a previously saved session by name."""
        path = self._path_for(name)
        if not path.is_file():
            raise FileNotFoundError(f"No saved session named {name!r}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[str]:
        """Return names of all saved sessions (sorted newest-first)."""
        files = sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        sessions = []
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append(data["name"])
            except (json.JSONDecodeError, KeyError):
                continue
        return sessions

    def append_message(self, session: dict, *, role: str, name: str, content: str) -> None:
        """Append a message to the session and auto-save."""
        session["messages"].append({
            "role": role,
            "name": name,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.save(session)

    # -- internal ------------------------------------------------------------

    def _path_for(self, name: str) -> Path:
        """Compute the file path for a session name (sanitised)."""
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
        return self._dir / f"{safe}.json"

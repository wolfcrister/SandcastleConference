"""Persona Registry — loads and validates agent definitions from personas.json."""

import json
from pathlib import Path

_REQUIRED_FIELDS = {"name", "avatar", "role", "system_prompt", "tools"}
_REGISTRY_PATH = Path(__file__).parent / "personas.json"


class PersonaRegistry:
    """Read-only registry backed by personas.json."""

    def __init__(self, path: Path | None = None):
        self._path = path or _REGISTRY_PATH
        self._personas: list[dict] = []
        self.load()

    # -- public API ----------------------------------------------------------

    def load(self) -> list[dict]:
        """(Re-)load personas from disk and validate."""
        raw = self._path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("personas.json must contain a JSON array.")
        names_seen: set[str] = set()
        for idx, entry in enumerate(data):
            missing = _REQUIRED_FIELDS - set(entry.keys())
            if missing:
                raise ValueError(
                    f"Persona at index {idx} is missing fields: {missing}"
                )
            name = entry["name"]
            if name in names_seen:
                raise ValueError(f"Duplicate persona name: {name!r}")
            names_seen.add(name)
        self._personas = data
        return data

    def get(self, name: str) -> dict:
        """Return a single persona dict by exact name."""
        for p in self._personas:
            if p["name"] == name:
                return p
        raise KeyError(f"Persona not found: {name!r}")

    def list_names(self) -> list[str]:
        """Return all available persona names."""
        return [p["name"] for p in self._personas]

    def all(self) -> list[dict]:
        """Return the full list of persona dicts."""
        return list(self._personas)

    # -- mutation API --------------------------------------------------------

    def add(self, persona: dict) -> None:
        """Add a new persona and persist to disk."""
        missing = _REQUIRED_FIELDS - set(persona.keys())
        if missing:
            raise ValueError(f"New persona is missing fields: {missing}")
        if any(p["name"] == persona["name"] for p in self._personas):
            raise ValueError(f"Persona name already exists: {persona['name']!r}")
        self._personas.append(persona)
        self._save()

    def update(self, name: str, updates: dict) -> dict:
        """Update fields of an existing persona and persist."""
        persona = self.get(name)
        if "name" in updates and updates["name"] != name:
            if any(p["name"] == updates["name"] for p in self._personas):
                raise ValueError(f"Name already taken: {updates['name']!r}")
        persona.update(updates)
        self._save()
        return persona

    def delete(self, name: str) -> None:
        """Remove a persona by name and persist."""
        self._personas = [p for p in self._personas if p["name"] != name]
        self._save()

    def _save(self) -> None:
        """Write current personas list back to disk."""
        self._path.write_text(
            json.dumps(self._personas, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

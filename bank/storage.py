"""Simple JSON file persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class JsonStorage:
    """Saves and loads the bank's state as a JSON file."""

    def __init__(self, path: str = "data/bank_data.json"):
        self.path = Path(path)

    def load(self) -> dict | None:
        """Return the saved data, or None if nothing has been saved yet."""
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def save(self, data: dict) -> None:
        """Write data atomically so a crash mid-write can't corrupt the file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
            os.replace(temp_name, self.path)
        except BaseException:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

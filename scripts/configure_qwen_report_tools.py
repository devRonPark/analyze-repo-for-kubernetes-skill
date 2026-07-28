#!/usr/bin/env python3
"""Register the local report lifecycle MCP server in Qwen settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any


SERVER_NAME = "analyze-repo-report-lifecycle"


def settings_path() -> Path:
    return Path.home() / ".qwen" / "settings.json"


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Qwen settings could not be read as JSON") from exc
    if not isinstance(loaded, dict):
        raise ValueError("Qwen settings must be a JSON object")
    return loaded


def write_settings_atomically(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    encoded = (json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(previous_mode)
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def configure(plugin_root: Path) -> None:
    resolved_root = plugin_root.resolve()
    settings_file = settings_path()
    settings = load_settings(settings_file)
    servers = settings.get("mcpServers")
    if servers is None:
        servers = {}
        settings["mcpServers"] = servers
    if not isinstance(servers, dict):
        raise ValueError("Qwen mcpServers must be a JSON object")

    servers[SERVER_NAME] = {
        "type": "stdio",
        "command": "python3",
        "args": [str(resolved_root / "mcp/report_tool_server.py")],
    }
    write_settings_atomically(settings_file, settings)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: configure_qwen_report_tools.py PLUGIN_ROOT", file=sys.stderr)
        return 2
    try:
        configure(Path(argv[0]))
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("오류: Qwen settings could not be updated", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

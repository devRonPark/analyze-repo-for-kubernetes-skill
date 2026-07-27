from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Protocol


@dataclass(frozen=True)
class RuntimeSignal:
    kind: str
    line: int
    data: dict[str, Any]


@dataclass(frozen=True)
class RuntimeExtractionOutcome:
    signals: list[RuntimeSignal]


class RuntimeSignalExtractor(Protocol):
    language: str
    name: str
    version: str

    def extract(self, path: str, lines: list[str]) -> RuntimeExtractionOutcome: ...


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (
        bool({"test", "tests", "__tests__"} & set(parts))
        or name.endswith((".test.js", ".test.jsx", ".test.ts", ".test.tsx", ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx"))
    )


def has_code_token(line: str, token: str) -> bool:
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if line.startswith("//", index) or char == "#":
            return False
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        if line.startswith(token, index):
            return True
        index += 1
    return False


class NodeRuntimeSignalExtractor:
    language = "node"
    name = "node_runtime_signals"
    version = "1.0.0"

    def extract(self, path: str, lines: list[str]) -> RuntimeExtractionOutcome:
        if is_test_path(path):
            return RuntimeExtractionOutcome([])
        signals: list[RuntimeSignal] = []
        for line_number, line in enumerate(lines, start=1):
            for match in re.finditer(r"process\.env\.([A-Z][A-Z0-9_]*)", line):
                if has_code_token(line, match.group(0)):
                    signals.append(RuntimeSignal("runtime_config_read", line_number, {"language": self.language, "key": match.group(1)}))
            if has_code_token(line, ".listen"):
                port = re.search(r"\|\|\s*(\d{1,5})", line)
                host = re.search(r"(?:,\s*)['\"]([^'\"]+)['\"]\s*\)?\s*$", line)
                if port:
                    data: dict[str, Any] = {"language": self.language, "port": int(port.group(1))}
                    if host:
                        data["host"] = host.group(1)
                    signals.append(RuntimeSignal("runtime_listener", line_number, data))
            if has_code_token(line, "new Client") and has_code_token(line, "connectionString"):
                config = re.search(r"connectionString\s*:\s*process\.env\.([A-Z][A-Z0-9_]*)", line)
                if config:
                    signals.append(RuntimeSignal("runtime_outbound_connection", line_number, {"language": self.language, "mechanism": "connection_string", "config_key": config.group(1)}))
            if has_code_token(line, "fs.writeFile"):
                config = re.search(r"fs\.writeFile\(\s*process\.env\.([A-Z][A-Z0-9_]*)", line)
                if config:
                    signals.append(RuntimeSignal("runtime_writable_path", line_number, {"language": self.language, "path_config_key": config.group(1)}))
            if has_code_token(line, "setInterval"):
                signals.append(RuntimeSignal("runtime_background_registration", line_number, {"language": self.language, "registration": "setInterval"}))
        return RuntimeExtractionOutcome(signals)


class PythonRuntimeSignalExtractor:
    language = "python"
    name = "python_runtime_signals"
    version = "1.0.0"

    def extract(self, path: str, lines: list[str]) -> RuntimeExtractionOutcome:
        if is_test_path(path):
            return RuntimeExtractionOutcome([])
        signals: list[RuntimeSignal] = []
        for line_number, line in enumerate(lines, start=1):
            for match in re.finditer(r"os\.(?:getenv\(\s*['\"]|environ\[\s*['\"])([A-Z][A-Z0-9_]*)", line):
                if has_code_token(line, match.group(0).split("(")[0]):
                    signals.append(RuntimeSignal("runtime_config_read", line_number, {"language": self.language, "key": match.group(1)}))
            if has_code_token(line, "uvicorn.run") or has_code_token(line, ".run"):
                port = re.search(r"\bport\s*=\s*(\d{1,5})", line)
                host = re.search(r"\bhost\s*=\s*['\"]([^'\"]+)['\"]", line)
                if port and (has_code_token(line, "uvicorn.run") or has_code_token(line, "app.run")):
                    data: dict[str, Any] = {"language": self.language, "port": int(port.group(1))}
                    if host:
                        data["host"] = host.group(1)
                    signals.append(RuntimeSignal("runtime_listener", line_number, data))
            if has_code_token(line, "requests.get") and ("os.getenv" in line or "os.environ" in line):
                key = re.search(r"os\.(?:getenv\(\s*['\"]|environ\[\s*['\"])([A-Z][A-Z0-9_]*)", line)
                if key:
                    signals.append(RuntimeSignal("runtime_outbound_connection", line_number, {"language": self.language, "mechanism": "http", "config_key": key.group(1)}))
            if has_code_token(line, "open") and re.search(r"['\"]w['\"]", line):
                key = re.search(r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]*)", line)
                if key:
                    signals.append(RuntimeSignal("runtime_writable_path", line_number, {"language": self.language, "path_config_key": key.group(1)}))
            if has_code_token(line, ".add_job"):
                signals.append(RuntimeSignal("runtime_background_registration", line_number, {"language": self.language, "registration": "scheduler.add_job"}))
        return RuntimeExtractionOutcome(signals)


EXTRACTORS: dict[str, RuntimeSignalExtractor] = {
    "node": NodeRuntimeSignalExtractor(),
    "python": PythonRuntimeSignalExtractor(),
}


def runtime_extractor_for(language: str | None) -> RuntimeSignalExtractor | None:
    return EXTRACTORS.get(language)

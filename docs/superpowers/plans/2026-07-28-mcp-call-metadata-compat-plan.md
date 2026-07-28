# MCP `tools/call` Metadata Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Qwen Code's standard MCP `tools/call` envelope metadata without changing the four report lifecycle tools or their handler arguments.

**Architecture:** Keep envelope validation in `mcp/report_tool_server.py`. Accept required `name` and `arguments` plus MCP `_meta` and task-augmentation `task`; discard the latter two before constructing `CompleteToolCall`. Continue rejecting every other envelope field.

**Tech Stack:** Python 3, stdlib JSON-RPC stdio server, `unittest`, Qwen Code 0.21.0 interactive MCP smoke test.

## Global Constraints

- Preserve the exact four tool names: `report_session_start`, `report_chunk_submit`, `report_session_sync`, `report_session_finalize`.
- Preserve the current `CompleteToolCall(name, arguments)` handler boundary.
- Accept `_meta` and `task` only as MCP envelope fields; do not pass either into lifecycle arguments.
- Continue rejecting unsupported envelope fields with JSON-RPC `-32602`.
- Keep all changes on `issue/71-mcp-metadata-compat` and reference GitHub Issue `#71` in commits.

---

### Task 1: Add the failing MCP metadata regression test

**Files:**
- Modify: `tests/test_report_tool_server.py` near the existing JSON-RPC `tools/call` contract test

**Interfaces:**
- Consumes: the existing `run_server()` test helper and `report_session_sync` fixture arguments.
- Produces: a red test proving `_meta` and `task` are accepted while unsupported envelope keys remain rejected.

- [ ] **Step 1: Write the failing test**

Add a JSON-RPC request whose `tools/call` params contain the existing `name` and `arguments`, plus `"_meta": {"progressToken": "qwen-progress-1"}` and `"task": {"ttl": 1000}`. Assert a successful `report_session_sync` result with the same session id. Add a second request with an unsupported envelope key such as `"unexpected": True` and assert a JSON-RPC error with code `-32602`.

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 -m unittest tests.test_report_tool_server -v
```

Expected: the metadata case fails with `MCP error -32602: tools/call requires only name and arguments` before production code changes.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_report_tool_server.py
git commit -m "test: cover MCP tools call metadata" -m "refs #71"
```

### Task 2: Relax only the MCP envelope allowlist

**Files:**
- Modify: `mcp/report_tool_server.py:133-148`

**Interfaces:**
- Consumes: validated JSON-RPC `tools/call` params.
- Produces: the same `CompleteToolCall(name, dict(arguments))` invocation, with `_meta` and `task` excluded.

- [ ] **Step 1: Add the minimal allowlist check**

Replace exact-key equality with an unsupported-key check equivalent to:

```python
allowed = {"name", "arguments", "_meta", "task"}
unsupported = set(values) - allowed
if unsupported:
    raise JsonRpcError(-32602, "tools/call contains unsupported parameters")
```

Leave `name` and `arguments` validation and `CompleteToolCall` construction unchanged. Do not validate or forward `_meta` or `task`.

- [ ] **Step 2: Run the focused tests to verify they pass**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 -m unittest tests.test_report_tool_server -v
```

Expected: all report tool server tests pass, including metadata acceptance and unknown-field rejection.

- [ ] **Step 3: Commit the minimal implementation**

```bash
git add mcp/report_tool_server.py
git commit -m "fix: accept MCP call metadata" -m "refs #71"
```

### Task 3: Run full regression validation and the Qwen smoke test

**Files:**
- No additional source files; inspect commits and generated test artifacts only.

**Interfaces:**
- Consumes: the tested MCP server and installed skill symlink.
- Produces: full test evidence and a Qwen interactive run that reaches `report_session_start` without the envelope error.

- [ ] **Step 1: Run the full unit suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts python3 -m unittest discover -s tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run package validation**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_plugin_package.py
```

Expected: the plugin package is valid.

- [ ] **Step 3: Run the Qwen interactive smoke test**

Install the branch checkout with `scripts/install-qwen.sh`, launch Qwen with TTY and `TERM=xterm-256color DEBUG=1 DEBUG_MODE=1 QWEN_DEBUG_LOG_FILE=/tmp/qwen-mcp-metadata-compat-20260728.log`, and run the jpetstore prompt. Confirm the debug log has no `tools/call requires only name and arguments` error and that the report session database records a created session or later lifecycle progress.

- [ ] **Step 4: Inspect the final diff and status**

Run:

```bash
git diff origin/main...HEAD --check
git status --short --branch
git log --oneline -5
```

Expected: only the spec, plan, MCP server, and focused regression test are changed on the issue branch; no generated report or cache is committed.

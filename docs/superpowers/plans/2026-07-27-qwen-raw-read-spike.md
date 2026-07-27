# Qwen raw-read spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 같은 Qwen 런타임에서 raw-read arm과 evidence arm을 각각 한 번 실행해, 어느 쪽이 계약을 통과하고 context를 덜 쓰는지 숫자로 확정한다.

**Architecture:** 버리는 spike 스크립트 두 개(workspace builder, run record extractor)를 scratchpad에 만들고, 기존 `scripts/plain_remote_git_clone.py`와 `scripts/repository_evidence.py`와 `scripts/validate_report.py`를 그대로 호출한다. 저장소에 커밋하는 산출물은 측정 보고서 한 개뿐이다.

**Tech Stack:** Python 3 (표준 라이브러리만), git, Qwen Code CLI `0.21.0`

**관련 문서:**
- Spec: `docs/superpowers/specs/2026-07-27-qwen-raw-read-spike-design.md`
- Issue: #58
- Branch: `issue/58-qwen-raw-read-spike`

## Global Constraints

- 모든 작업은 `issue/58-qwen-raw-read-spike` 브랜치에서 한다. `main`에 직접 커밋하지 않는다.
- 커밋 subject 또는 body에 `refs #58`을 포함한다.
- GitHub Issue, PR, 검증 노트는 한국어로 쓴다.
- spike 스크립트는 커밋하지 않는다. `SCRATCH` 아래에만 둔다.
- 커밋하는 파일은 `validation/qwen-raw-read-spike-2026-07-27.md` 하나뿐이다.
- 작업 트리에 이미 있는 미커밋 변경(`hooks.json` 삭제, `AGENTS.md`, `docs/troubleshooting/`, `hooks.json.disabled`)은 건드리지 않는다. `git add -A`를 쓰지 않는다.
- 분석 대상 repository: `https://github.com/spring-projects/spring-petclinic`
- 분석 대상 revision: `f182358d02e4a68e52bdbabf55ca7800288511e7` (기존 baseline과 동일 커밋)
- 분석 목적: `전체 상세 보고서` (`full_repository_assessment` / `output_mode: detailed`)
- 두 arm의 입력은 배타적이다. arm A는 evidence JSON을 받지 않고, arm B는 workspace 경로를 받지 않는다.
- 대상 repository의 script, build, test, migration, server, container 명령은 실행하지 않는다.

## 경로 규약

모든 task는 아래 두 변수를 쓴다. 매 쉘 세션 시작 시 export한다.

```bash
export SKILL_ROOT=/home/daolts/analyze-repo-for-kubernetes-skill
export SCRATCH=/tmp/claude-1000/-home-daolts-analyze-repo-for-kubernetes-skill/fa48f703-c02b-49f7-b91c-2b04d06bd3ea/scratchpad/spike
mkdir -p "$SCRATCH"
```

## 확인 완료된 사실

spec의 `미확인 항목` 세 가지는 계획 작성 중에 모두 해소되었다. 아래는 실제 확인 결과이며, 계획은 이 사실 위에 서 있다.

| 항목 | 결과 |
| --- | --- |
| 비대화형 실행 | `qwen -p "<prompt>" -o json`. Qwen Code `0.21.0` 확인. 인증은 `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` 환경 변수만으로 동작 |
| token usage 노출 | `-o json` 스트림의 `type: "result"` 이벤트에 `usage.input_tokens`, `usage.output_tokens`, `usage.cache_read_input_tokens`, `usage.total_tokens`, `duration_ms`, `num_turns` 포함 |
| 읽은 파일 목록 추출 | `-o json` 스트림의 `message.content[]` 안 `type: "tool_use"` 블록에 `read_file`의 `file_path`, `list_directory`의 `path`가 그대로 들어 있음. telemetry나 atime fallback 불필요 |

기존 벤치 하네스 `/tmp/qwen-skill-bench.kQ6peY/`에 실제 실행 4건이 남아 있다. 이 중 `runs/run4.redacted.json`을 extractor 검증용 golden fixture로 쓴다. 해당 실행의 알려진 값은 아래와 같고, `qwen-home/usage_record.jsonl`의 session `b4f143ef`와 일치한다.

| 항목 | 값 |
| --- | --- |
| `duration_ms` | `175123` |
| `num_turns` | `17` |
| `usage.input_tokens` | `424480` |
| `usage.output_tokens` | `3027` |
| `read_file` 호출 수 | `10` |
| `list_directory` 호출 수 | `6` |
| 전체 tool call 수 | `16` |

## File Structure

| 파일 | 책임 | 커밋 |
| --- | --- | --- |
| `$SCRATCH/build_workspace.py` | clone 결과를 최소 sanitize해서 workspace와 manifest 생성 | 안 함 |
| `$SCRATCH/extract_run.py` | Qwen `-o json` transcript에서 run record JSON 추출 | 안 함 |
| `$SCRATCH/prompt-arm-a.md` | arm A 프롬프트 | 안 함 |
| `$SCRATCH/prompt-arm-b.md` | arm B 프롬프트 | 안 함 |
| `validation/qwen-raw-read-spike-2026-07-27.md` | 측정 보고서와 판정 | 함 |

---

### Task 1: Qwen 비대화형 인증 확정 — 완료됨

**Files:**
- Create: `$SCRATCH/auth.env`

**Interfaces:**
- Consumes: 없음
- Produces: `$SCRATCH/auth.env`. Task 3, Task 4, Task 5가 source한다

**상태: 2026-07-27 해결 완료.** 계획 작성 중에 실제로 확인했으므로 재실행할 필요는 없으나, `$SCRATCH`가 사라졌으면 Step 1부터 다시 한다.

추론 엔드포인트는 sglang이며, 서빙 모델과 context 한도는 아래와 같다.

| 항목 | 값 |
| --- | --- |
| Endpoint | `http://172.16.4.249:30000/v1` |
| Auth type | `openai` (환경 변수만으로 충분. `settings.json` 불필요) |
| Model id | `/root/.cache/huggingface/models--Qwen--Qwen3-Coder-30B-A3B-Instruct/snapshots/b2cff646eb4bb1d68355c01b18ae02e7cf42d120` |
| `max_model_len` | `131072` |

- [x] **Step 1: 모델 id를 조회해 `auth.env` 생성**

```bash
MODEL=$(curl -s -m 10 http://172.16.4.249:30000/v1/models | python3 -c "import json,sys; print(json.load(sys.stdin)['data'][0]['id'])")
cat > "$SCRATCH/auth.env" <<EOF
export OPENAI_BASE_URL=http://172.16.4.249:30000/v1
export OPENAI_API_KEY=EMPTY
export OPENAI_MODEL='$MODEL'
EOF
cat "$SCRATCH/auth.env"
```

Expected: 세 줄 모두 출력. `OPENAI_API_KEY`는 sglang이 검증하지 않으므로 placeholder다.

- [x] **Step 2: smoke test로 인증과 도구 사용을 동시에 확인**

```bash
source "$SCRATCH/auth.env"
rm -rf "$SCRATCH/smoke" && mkdir -p "$SCRATCH/smoke/repo"
printf 'server:\n  port: 8080\n' > "$SCRATCH/smoke/repo/application.yml"
cd "$SCRATCH/smoke/repo"
timeout 300 qwen -p "Read application.yml in the current directory and reply with only the port number." -o json > "$SCRATCH/smoke/out.json" 2> "$SCRATCH/smoke/err.txt"
echo "exit=$?"
```

Expected: `exit=0`.

- [x] **Step 3: smoke transcript에 tool_use와 usage가 들어 있는지 확인**

```bash
python3 -c "
import json
events = json.load(open('$SCRATCH/smoke/out.json'))
names = [b['name'] for e in events for b in ((e.get('message') or {}).get('content') or []) if isinstance(b, dict) and b.get('type') == 'tool_use']
result = next(e for e in events if e.get('type') == 'result')
print('tool_use:', names)
print('usage:', result.get('usage'))
assert 'read_file' in names, 'read_file tool_use not found in transcript'
assert result.get('is_error') is False, 'run reported an error'
print('OK')
"
```

실제 확인 결과: `tool_use: ['read_file']`, `is_error: False`, `duration_ms: 11032`, `num_turns: 2`, `usage.input_tokens: 30268`, 응답 `8080`.

**측정에 직접 영향을 주는 발견:** 2줄짜리 파일 하나를 읽는 데 input token이 `30,268`개 들었다. 저장소 내용과 무관한 고정 비용이며, 원인은 Qwen이 주입하는 system prompt와 tool 정의다. `system/init` 이벤트의 `tools` 배열에는 `computer_use__*` 계열을 포함한 대량의 도구가 들어 있다.

이 고정 비용은 arm A와 arm B에 모두 붙지만 성격이 다르다. arm A는 매 request마다 tool 정의를 다시 싣고 turn 수만큼 누적된다. Task 6 보고서에서 두 arm의 token을 비교할 때 이 `약 30K` 고정 바닥을 명시하고, 순수 증분도 함께 제시한다.

- [x] **Step 4: 커밋 없음**

`auth.env`는 `$SCRATCH`에만 두고 커밋하지 않는다. 사용자의 `~/.bashrc`나 `~/.qwen/settings.json`은 수정하지 않았다.

---

### Task 2: Run record extractor

**Files:**
- Create: `$SCRATCH/extract_run.py`

**Interfaces:**
- Consumes: Task 1이 확인한 `-o json` transcript 형식
- Produces: `extract(transcript_path: Path, arm: str) -> dict`. 반환 dict의 키는 `arm`, `is_error`, `duration_ms`, `num_turns`, `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `total_tokens`, `tool_calls`, `read_file_count`, `list_directory_count`, `read_files`, `listed_directories`. Task 4와 Task 5가 이 dict를 run record JSON으로 저장한다

extractor는 spike에서 유일하게 조용히 틀릴 수 있는 코드다. 파싱을 잘못하면 잘못된 숫자가 그대로 판정에 들어간다. 그래서 새 실행에 쓰기 전에 값이 이미 알려진 기존 transcript로 먼저 검증한다.

- [ ] **Step 1: golden fixture가 존재하는지 확인**

```bash
ls -la /tmp/qwen-skill-bench.kQ6peY/runs/run4.redacted.json
```

Expected: 파일 존재. 없으면 멈추고 보고한다. `/tmp`는 재부팅으로 사라질 수 있으므로, 없으면 Step 2의 기대값을 검증할 방법이 없다.

- [ ] **Step 2: 실패하는 검증 스크립트를 먼저 작성**

```bash
cat > "$SCRATCH/test_extract_run.py" <<'PYEOF'
#!/usr/bin/env python3
"""Verify extract_run against a transcript whose values are already known."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_run import extract

GOLDEN = Path("/tmp/qwen-skill-bench.kQ6peY/runs/run4.redacted.json")
EXPECTED = {
    "is_error": False,
    "duration_ms": 175123,
    "num_turns": 17,
    "input_tokens": 424480,
    "output_tokens": 3027,
    "tool_calls": 16,
    "read_file_count": 10,
    "list_directory_count": 6,
}

record = extract(GOLDEN, arm="golden")
failures = [f"{k}: expected {v!r}, got {record.get(k)!r}" for k, v in EXPECTED.items() if record.get(k) != v]
if failures:
    print("FAIL")
    for failure in failures:
        print(" ", failure)
    raise SystemExit(1)
if len(record["read_files"]) != 10 or len(record["listed_directories"]) != 6:
    print("FAIL: read_files/listed_directories length mismatch")
    raise SystemExit(1)
print("PASS")
PYEOF
```

- [ ] **Step 3: 검증 스크립트를 돌려 실패를 확인**

```bash
cd "$SCRATCH" && python3 test_extract_run.py
```

Expected: FAIL. `ModuleNotFoundError: No module named 'extract_run'`.

- [ ] **Step 4: extractor 구현**

```bash
cat > "$SCRATCH/extract_run.py" <<'PYEOF'
#!/usr/bin/env python3
"""Extract one run record from a Qwen Code `-o json` transcript. Throwaway spike tool."""
from __future__ import annotations

import json
import sys
from pathlib import Path

READ_TOOLS = {"read_file": "file_path", "list_directory": "path"}


def extract(transcript_path: Path, arm: str) -> dict:
    events = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    reads: list[str] = []
    listings: list[str] = []
    tool_calls = 0
    for event in events:
        for block in (event.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool_calls += 1
            name = block.get("name")
            argument_key = READ_TOOLS.get(name)
            if argument_key is None:
                continue
            value = (block.get("input") or {}).get(argument_key)
            if value is None:
                continue
            (reads if name == "read_file" else listings).append(value)

    result = next((event for event in events if event.get("type") == "result"), None)
    if result is None:
        raise ValueError(f"transcript has no result event: {transcript_path}")
    usage = result.get("usage") or {}
    return {
        "arm": arm,
        "transcript": str(transcript_path),
        "is_error": result.get("is_error"),
        "error": (result.get("error") or {}).get("message"),
        "duration_ms": result.get("duration_ms"),
        "num_turns": result.get("num_turns"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "tool_calls": tool_calls,
        "read_file_count": len(reads),
        "list_directory_count": len(listings),
        "read_files": reads,
        "listed_directories": listings,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: extract_run.py <transcript.json> <arm>", file=sys.stderr)
        return 2
    record = extract(Path(sys.argv[1]), sys.argv[2])
    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
```

- [ ] **Step 5: 검증 스크립트를 돌려 통과를 확인**

```bash
cd "$SCRATCH" && python3 test_extract_run.py
```

Expected: `PASS`.

FAIL이면 extractor가 틀린 것이므로 Step 4로 돌아간다. 기대값을 실제 출력에 맞춰 고치지 않는다. 기대값은 `usage_record.jsonl` session `b4f143ef`에서 독립적으로 교차 확인된 값이다.

- [ ] **Step 6: 커밋 없음**

spike 스크립트는 커밋하지 않는다.

---

### Task 3: Workspace builder

**Files:**
- Create: `$SCRATCH/build_workspace.py`

**Interfaces:**
- Consumes: `scripts/repository_evidence.py`의 `resolve_roots`, `walk_text_files` (기존 함수, 수정하지 않음)
- Produces: `$SCRATCH/workspace/` 디렉터리와 `$SCRATCH/workspace-manifest.json`. Task 4가 workspace 경로를 arm A 입력으로 쓴다

최소 sanitize는 `.git`, `node_modules`, `build`, `dist`, `target`, binary 제외까지만 한다. 값 mask는 하지 않는다. 대상이 public repository라 이번 결론에 영향이 없다.

`repository_evidence.py`의 `walk_text_files`가 이미 정확히 이 필터를 수행하고 `FileRecord(path, size_bytes, extension, line_count)`를 돌려주므로 그대로 쓴다. 부수 효과로 이 함수의 재사용 가능성이 검증되고, 이후 공용 정책 모듈 결정의 입력이 된다.

- [ ] **Step 1: 대상 repository를 고정 revision으로 clone**

```bash
source "$SCRATCH/auth.env"
rm -rf "$SCRATCH/clone"
python3 "$SKILL_ROOT/scripts/plain_remote_git_clone.py" --url https://github.com/spring-projects/spring-petclinic --destination "$SCRATCH/clone" --revision f182358d02e4a68e52bdbabf55ca7800288511e7
```

Expected: `state` `resolved`, `revision`이 `f182358d02e4a68e52bdbabf55ca7800288511e7`로 끝나는 JSON 한 줄.

- [ ] **Step 2: workspace builder 작성**

```bash
cat > "$SCRATCH/build_workspace.py" <<'PYEOF'
#!/usr/bin/env python3
"""Copy a clone into a minimally sanitized analysis workspace. Throwaway spike tool."""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

SKILL_ROOT = Path(os.environ["SKILL_ROOT"])
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from repository_evidence import resolve_roots, walk_text_files  # noqa: E402


def build(clone_root: Path, workspace_root: Path) -> dict:
    if workspace_root.exists() or workspace_root.is_symlink():
        raise ValueError("workspace destination must not exist")
    repository_root, analysis_root, subdirectory = resolve_roots(clone_root, ".")
    records = walk_text_files(repository_root, analysis_root)
    workspace_root.mkdir(parents=True)
    for record in records:
        destination = workspace_root / record.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repository_root / record.path, destination)
    return {
        "clone_root": str(repository_root),
        "workspace_root": str(workspace_root.resolve()),
        "subdirectory": subdirectory,
        "file_count": len(records),
        "total_bytes": sum(record.size_bytes for record in records),
        "total_lines": sum(record.line_count for record in records),
        "files": [asdict(record) for record in records],
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: build_workspace.py <clone_root> <workspace_root>", file=sys.stderr)
        return 2
    manifest = build(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
```

- [ ] **Step 3: workspace 생성**

```bash
rm -rf "$SCRATCH/workspace"
python3 "$SCRATCH/build_workspace.py" "$SCRATCH/clone" "$SCRATCH/workspace" > "$SCRATCH/workspace-manifest.json"
python3 -c "
import json
m = json.load(open('$SCRATCH/workspace-manifest.json'))
print('file_count', m['file_count'], 'total_lines', m['total_lines'])
"
```

Expected: `file_count`가 0보다 큰 값.

- [ ] **Step 4: sanitize가 실제로 적용됐는지 확인**

```bash
python3 -c "
from pathlib import Path
ws = Path('$SCRATCH/workspace')
leaked = [str(p.relative_to(ws)) for p in ws.rglob('*') if p.is_file()
          and ({'.git', 'target', 'node_modules', 'build', 'dist'} & set(p.relative_to(ws).parts))]
assert not leaked, f'excluded paths leaked into workspace: {leaked[:5]}'
assert not (ws / '.git').exists(), '.git leaked into workspace'
print('sanitize OK')
"
```

Expected: `sanitize OK`.

- [ ] **Step 5: 커밋 없음**

---

### Task 4: Arm A 실행 (raw-read)

**Files:**
- Create: `$SCRATCH/prompt-arm-a.md`
- Create: `$SCRATCH/arm-a.transcript.json`, `$SCRATCH/arm-a.report.md`, `$SCRATCH/arm-a.record.json`

**Interfaces:**
- Consumes: Task 1의 `$SCRATCH/auth.env`, Task 2의 `extract_run.extract`, Task 3의 `$SCRATCH/workspace`
- Produces: `$SCRATCH/arm-a.record.json`. Task 6이 arm B record와 나란히 읽는다

- [ ] **Step 1: arm A 프롬프트 작성**

workspace 경로만 준다. evidence JSON은 주지 않는다.

```bash
cat > "$SCRATCH/prompt-arm-a.md" <<EOF
\`analyze-repo-for-kubernetes\` skill을 사용해서 아래 repository를 분석하세요.

분석 대상: Local directory path \`$SCRATCH/workspace\`
revision: \`f182358d02e4a68e52bdbabf55ca7800288511e7\`
subdirectory: \`.\`
목적: 전체 상세 보고서
출력: Markdown 상세 보고서, 한국어

제약:
- 분석 대상은 read-only로만 다룬다.
- dependency install, repository script, build, test, migration, server, container 실행은 하지 않는다.
- secret 값, \`.env\` 값, token, password, private key 값은 출력하지 말고 \`[REDACTED]\`로 처리한다.
- Kubernetes manifest, Dockerfile, Helm chart, application code는 생성하지 않는다.

완료 조건:
- 배포 대상 후보, 저장소에 정의된 런타임 의존성, 외부 런타임 의존성, 배포 대상 후보에서 제외한 항목을 근거와 함께 분리한다.
- 중요한 사실에는 \`path/to/file:line\` 형식의 인용을 남긴다.
- 각 배포 대상 후보에 build, production startup, runtime/framework, port 또는 non-listener, configuration 적용 시점, writable state, containerization status, Kubernetes 최소 설계 입력을 포함한다.
- 마지막은 \`설계 입력 충분\`, \`추가 정보 필요\`, \`분석 불가\` 중 하나로 끝낸다.
EOF
```

- [ ] **Step 2: skill이 Qwen에 설치되어 있는지 확인**

```bash
source "$SCRATCH/auth.env"
ls -la "${QWEN_HOME:-$HOME/.qwen}/skills/analyze-repo-for-kubernetes" 2>&1
```

없으면 설치한다.

```bash
QWEN_SKILLS_DIR="${QWEN_HOME:-$HOME/.qwen}/skills" bash "$SKILL_ROOT/scripts/install-qwen.sh"
```

Expected: `Qwen 스킬 설치 완료`.

- [ ] **Step 3: arm A 실행**

```bash
source "$SCRATCH/auth.env"
cd "$SCRATCH/workspace"
START=$(date +%s%3N)
timeout 3600 qwen -p "$(cat "$SCRATCH/prompt-arm-a.md")" -o json > "$SCRATCH/arm-a.transcript.json" 2> "$SCRATCH/arm-a.stderr"
echo "exit=$?"
END=$(date +%s%3N)
echo "WALL_MS=$((END - START))" | tee "$SCRATCH/arm-a.wall"
```

Expected: `exit=0`. 비정상 종료해도 transcript는 남으므로 Step 4로 진행하고, 실패 사실을 record에 남긴다.

- [ ] **Step 4: 보고서 본문 추출**

```bash
python3 -c "
import json
from pathlib import Path
events = json.load(open('$SCRATCH/arm-a.transcript.json'))
result = next(e for e in events if e.get('type') == 'result')
Path('$SCRATCH/arm-a.report.md').write_text(result.get('result') or '', encoding='utf-8')
print('report bytes:', len(result.get('result') or ''))
"
```

Expected: 0보다 큰 바이트 수.

- [ ] **Step 5: run record 생성**

```bash
cd "$SCRATCH" && python3 extract_run.py arm-a.transcript.json raw-read > arm-a.record.json
python3 -c "
import json
r = json.load(open('$SCRATCH/arm-a.record.json'))
print({k: r[k] for k in ('is_error','duration_ms','num_turns','input_tokens','output_tokens','tool_calls','read_file_count')})
"
```

- [ ] **Step 6: 계약 검증**

```bash
python3 "$SKILL_ROOT/scripts/validate_report.py" "$SCRATCH/arm-a.report.md" --mode detailed --repo-root "$SCRATCH/workspace" > "$SCRATCH/arm-a.validate.txt" 2>&1
echo "validate_exit=$?" | tee -a "$SCRATCH/arm-a.validate.txt"
```

통과와 실패 모두 유효한 결과다. 실패해도 여기서 멈추지 않는다. 종료 코드와 출력을 그대로 보존한다.

- [ ] **Step 7: 커밋 없음**

---

### Task 5: Arm B 실행 (evidence)

**Files:**
- Create: `$SCRATCH/prompt-arm-b.md`
- Create: `$SCRATCH/evidence.json`, `$SCRATCH/arm-b.transcript.json`, `$SCRATCH/arm-b.report.md`, `$SCRATCH/arm-b.record.json`

**Interfaces:**
- Consumes: Task 1의 `$SCRATCH/auth.env`, Task 2의 `extract_run.extract`, Task 3의 `$SCRATCH/clone`
- Produces: `$SCRATCH/arm-b.record.json`

arm B는 evidence JSON만 받는다. workspace 경로를 주지 않는다. 입력을 섞으면 대조가 성립하지 않는다.

- [ ] **Step 1: evidence 수집**

```bash
START=$(date +%s%3N)
python3 "$SKILL_ROOT/scripts/repository_evidence.py" "$SCRATCH/clone" --output "$SCRATCH/evidence.json"
END=$(date +%s%3N)
echo "SCANNER_MS=$((END - START))" | tee "$SCRATCH/arm-b.scanner"
python3 -c "
import json
d = json.load(open('$SCRATCH/evidence.json'))
print('files', len(d['snapshot']['files']), 'evidence', len(d['evidence']))
"
```

Expected: `evidence` 개수가 0보다 큼. scanner wall time도 보고서에 기록한다.

- [ ] **Step 2: arm B 프롬프트 작성**

```bash
cat > "$SCRATCH/prompt-arm-b.md" <<EOF
아래는 \`analyze-repo-for-kubernetes\` skill의 deterministic scanner가 수집한 evidence JSON입니다.
이 evidence만 근거로 Kubernetes 이관 분석 보고서를 작성하세요.

분석 대상 revision: \`f182358d02e4a68e52bdbabf55ca7800288511e7\`
목적: 전체 상세 보고서
출력: Markdown 상세 보고서, 한국어

제약:
- 저장소 파일을 직접 읽지 않는다. 아래 evidence JSON만 사용한다.
- evidence에 없는 사실을 만들어내지 않는다. 근거가 없으면 \`미확인\`으로 기록한다.
- secret 값은 출력하지 않는다.
- Kubernetes manifest, Dockerfile, Helm chart, application code는 생성하지 않는다.

완료 조건:
- 배포 대상 후보, 저장소에 정의된 런타임 의존성, 외부 런타임 의존성, 배포 대상 후보에서 제외한 항목을 근거와 함께 분리한다.
- 중요한 사실에는 \`path/to/file:line\` 형식의 인용을 남긴다.
- 각 배포 대상 후보에 build, production startup, runtime/framework, port 또는 non-listener, configuration 적용 시점, writable state, containerization status, Kubernetes 최소 설계 입력을 포함한다.
- 마지막은 \`설계 입력 충분\`, \`추가 정보 필요\`, \`분석 불가\` 중 하나로 끝낸다.

evidence JSON:

\`\`\`json
$(cat "$SCRATCH/evidence.json")
\`\`\`
EOF
wc -c "$SCRATCH/prompt-arm-b.md"
```

- [ ] **Step 3: arm B 실행**

cwd는 evidence를 읽을 필요가 없도록 빈 디렉터리로 둔다.

```bash
source "$SCRATCH/auth.env"
mkdir -p "$SCRATCH/arm-b-cwd"
cd "$SCRATCH/arm-b-cwd"
START=$(date +%s%3N)
timeout 3600 qwen -p "$(cat "$SCRATCH/prompt-arm-b.md")" -o json > "$SCRATCH/arm-b.transcript.json" 2> "$SCRATCH/arm-b.stderr"
echo "exit=$?"
END=$(date +%s%3N)
echo "WALL_MS=$((END - START))" | tee "$SCRATCH/arm-b.wall"
```

- [ ] **Step 4: 보고서 본문 추출**

```bash
python3 -c "
import json
from pathlib import Path
events = json.load(open('$SCRATCH/arm-b.transcript.json'))
result = next(e for e in events if e.get('type') == 'result')
Path('$SCRATCH/arm-b.report.md').write_text(result.get('result') or '', encoding='utf-8')
print('report bytes:', len(result.get('result') or ''))
"
```

- [ ] **Step 5: run record 생성**

```bash
cd "$SCRATCH" && python3 extract_run.py arm-b.transcript.json evidence > arm-b.record.json
python3 -c "
import json
r = json.load(open('$SCRATCH/arm-b.record.json'))
print({k: r[k] for k in ('is_error','duration_ms','num_turns','input_tokens','output_tokens','tool_calls','read_file_count')})
"
```

Expected: `read_file_count`가 `0`이거나 매우 낮음. 높으면 arm B가 파일을 직접 읽은 것이므로 대조가 오염됐다. 그 경우 사실을 보고서에 기록하고 판정에서 그 한계를 명시한다.

- [ ] **Step 6: 계약 검증**

```bash
python3 "$SKILL_ROOT/scripts/validate_report.py" "$SCRATCH/arm-b.report.md" --mode detailed --repo-root "$SCRATCH/clone" > "$SCRATCH/arm-b.validate.txt" 2>&1
echo "validate_exit=$?" | tee -a "$SCRATCH/arm-b.validate.txt"
```

- [ ] **Step 7: 커밋 없음**

---

### Task 6: 측정 보고서 작성과 판정

**Files:**
- Create: `validation/qwen-raw-read-spike-2026-07-27.md`

**Interfaces:**
- Consumes: `$SCRATCH/arm-a.record.json`, `$SCRATCH/arm-b.record.json`, 두 `*.validate.txt`, `$SCRATCH/workspace-manifest.json`, `$SCRATCH/arm-b.scanner`
- Produces: 커밋된 측정 보고서와 다음 단계 판정

- [ ] **Step 1: 비교표 데이터 생성**

```bash
python3 -c "
import json
rows = []
for arm in ('a', 'b'):
    r = json.load(open(f'$SCRATCH/arm-{arm}.record.json'))
    rows.append(r)
keys = ('arm','is_error','duration_ms','num_turns','input_tokens','output_tokens','cache_read_input_tokens','total_tokens','tool_calls','read_file_count','list_directory_count')
print('| 항목 | ' + ' | '.join(r['arm'] for r in rows) + ' |')
print('| --- | ' + ' | '.join('---' for _ in rows) + ' |')
for k in keys[1:]:
    print(f'| {k} | ' + ' | '.join(str(r.get(k)) for r in rows) + ' |')
" | tee "$SCRATCH/comparison.md"
```

- [ ] **Step 2: 읽은 파일 목록 확인**

```bash
python3 -c "
import json
r = json.load(open('$SCRATCH/arm-a.record.json'))
print('arm A read_files:')
for p in r['read_files']:
    print(' ', p)
"
```

- [ ] **Step 3: 보고서 작성**

`validation/qwen-raw-read-spike-2026-07-27.md`를 만든다. `validation/debug-bottleneck-analysis-2026-07-24.md`의 구성을 따른다. 반드시 포함할 섹션:

1. **분석 목적** — spec이 검증하려는 가설을 그대로 인용
2. **실행 조건** — 실행 일자, 대상 repository와 revision, 목적, Qwen 버전 `0.21.0`, 사용 모델, 두 arm의 입력
3. **측정 결과** — Step 1의 비교표. 값은 record JSON에서 그대로 옮긴다
4. **계약 검증 결과** — 두 `*.validate.txt`의 종료 코드와 실패 사유
5. **arm A가 읽은 파일** — Step 2 목록과 개수. workspace manifest의 전체 파일 수와 함께 비율로 제시
6. **참고치** — Codex baseline `408.93s` / input `1,320,986` token. **결론 근거로 쓰지 않는다**고 명시
7. **판정** — spec의 결정 규칙 표 중 어느 행에 해당하는지와 그 근거
8. **다음 단계** — 판정에 따른 후속 슬라이스 제안

측정하지 못한 항목은 `미측정`으로 표기한다. 값을 추정해서 채우지 않는다.

- [ ] **Step 4: 보고서에 미해결 항목이 없는지 확인**

저장소의 기존 validator를 쓴다. `scripts/validate_skill.py:108`이 이미 placeholder 패턴을 검사하므로 패턴을 여기서 다시 쓰지 않는다. 패턴 문자열을 문서에 그대로 적으면 그 문서 자체가 검사에 걸린다.

```bash
python3 "$SKILL_ROOT/scripts/validate_skill.py" "$SKILL_ROOT"
```

Expected: 종료 코드 `0`.

`hooks.json` 관련 실패가 나오면 그것은 이 spike와 무관한 작업 트리의 기존 상태이므로 Step 5로 진행한다. 보고서 파일 이름이 언급된 placeholder 실패만 이 task의 책임이다.

- [ ] **Step 5: 보고서 파일 하나만 커밋**

```bash
cd "$SKILL_ROOT"
git add validation/qwen-raw-read-spike-2026-07-27.md
git status --short
```

Expected: `A  validation/qwen-raw-read-spike-2026-07-27.md` 한 줄만 staged. 다른 파일이 staged면 `git restore --staged`로 뺀다.

```bash
git commit -m "$(cat <<'EOF'
docs: add Qwen raw-read spike measurement

refs #58

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: spec의 미확인 항목 갱신**

`docs/superpowers/specs/2026-07-27-qwen-raw-read-spike-design.md`의 `미확인 항목` 절을 이 계획의 `확인 완료된 사실` 표 내용으로 교체한다. 그리고 커밋한다.

```bash
git add docs/superpowers/specs/2026-07-27-qwen-raw-read-spike-design.md
git commit -m "$(cat <<'EOF'
docs: resolve spike design unknowns

refs #58

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Spec 요구사항 | 담당 Task |
| --- | --- |
| 산출물은 측정 보고서 하나, spike 스크립트는 커밋 안 함 | Global Constraints, Task 6 Step 5 |
| arm A raw-read / arm B evidence, 입력 배타 | Task 4 Step 1, Task 5 Step 2·Step 3 |
| revision을 baseline과 동일 커밋으로 고정 | Task 3 Step 1 |
| 기존 clone 스크립트 재사용 | Task 3 Step 1 |
| 최소 sanitize, `EXCLUDED_PATH_PARTS`/`is_generated_path`/`is_binary_file` 재사용 | Task 3 Step 2 (`walk_text_files`가 세 가지를 모두 적용) |
| 값 mask 하지 않음 | Task 3 Step 2 |
| wall time 측정 | Task 4 Step 3, Task 5 Step 3 |
| token usage 측정 | Task 2, Task 4 Step 5, Task 5 Step 5 |
| `validate_report.py` 통과 여부 | Task 4 Step 6, Task 5 Step 6 |
| 읽은 파일 목록과 개수 | Task 2, Task 6 Step 2 |
| Codex baseline은 참고치로만 | Task 6 Step 3 항목 6 |
| 자동 임계값 없이 수동 판단 | Task 6 Step 3 항목 7 |
| 미측정 항목은 그대로 표기 | Task 6 Step 3 마지막 문장 |

**타입 일관성:** `extract()`가 만드는 키 이름을 Task 4 Step 5, Task 5 Step 5, Task 6 Step 1이 그대로 쓴다. `walk_text_files`는 `FileRecord(path, size_bytes, extension, line_count)`를 돌려주며 Task 3 Step 2의 manifest가 이 필드명을 그대로 쓴다.

**남은 위험:**

- ~~Task 1의 인증~~ — 2026-07-27 해결됨. 차단 요인 아님.
- `/tmp/qwen-skill-bench.kQ6peY/runs/run4.redacted.json`이 사라지면 Task 2의 extractor 검증 근거가 없어진다. Task 2 Step 1에서 먼저 확인한다.
- arm B 프롬프트에 evidence JSON 전체를 인라인으로 넣는데, 모델 `max_model_len`이 `131072`이고 system prompt와 tool 정의만으로 이미 약 `30K`가 소모된다. 즉 evidence JSON에 실질적으로 쓸 수 있는 예산은 약 `100K` token이다. Task 5 Step 1 직후 `evidence.json` 크기를 확인해 예산을 넘길 것 같으면 실행 전에 보고한다. 넘쳐서 실패하면 그 실패 자체가 "evidence 전량 주입" 방식의 한계로서 유효한 측정 결과이므로 보고서에 그대로 기록한다.
- 두 arm 모두 약 `30K` token의 고정 바닥을 공유한다. 절대값만 비교하면 차이가 실제보다 작아 보인다. Task 6에서 고정 바닥을 뺀 증분도 함께 제시한다.

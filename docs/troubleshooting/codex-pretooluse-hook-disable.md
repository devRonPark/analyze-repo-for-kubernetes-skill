  # Codex PreToolUse hook 차단 트러블슈팅

  ## 증상

  Codex가 Bash, apply_patch, pwd 같은 단순 도구 실행도 하지 못하고 아래 메시지로 차단된다.

  ```text
  Command blocked by PreToolUse hook: 이 분석 결과를 어디에 활용하시나요? Target은 확정됐지만 분석 목적이 아직 확정되지
  않았습니다.

  ## 원인

  전역 Codex 설정 파일에 PreToolUse hook이 등록되어 있었다.

  /home/daolts/.codex/config.toml

  문제가 된 설정은 대략 다음 형태다.

  [[hooks.PreToolUse]]
  matcher = ".*"
  [[hooks.PreToolUse.hooks]]
  type = "command"
  command = "python3 /home/daolts/.agents/skills/analyze-repo-for-kubernetes/scripts/codex_target_gate_hook.py"
  timeout = 2
  statusMessage = "Kubernetes 분석 대상 확인 중"

  이 hook은 모든 tool 실행 전에 먼저 실행된다. 그래서 Codex에게 승인을 줘도 Bash 실행 자체가 hook에서 먼저 막힐 수 있다.

  ## 확인 방법

  nl -ba /home/daolts/.codex/config.toml | sed -n '65,100p'

  또는:

  rg -n "PreToolUse|pre_tool_use|codex_target_gate_hook" /home/daolts/.codex/config.toml

  ## 비활성화 전 백업

  항상 먼저 백업한다.

  cp /home/daolts/.codex/config.toml /home/daolts/.codex/config.toml.bak.$(date +%Y%m%d-%H%M%S).pretooluse-disable

  ## 초보자에게 가장 쉬운 해결 방법

  파일을 직접 연다.

  nano /home/daolts/.codex/config.toml

  아래 블록을 삭제한다.

  [[hooks.PreToolUse]]
  matcher = ".*"
  [[hooks.PreToolUse.hooks]]
  type = "command"
  command = "python3 /home/daolts/.agents/skills/analyze-repo-for-kubernetes/scripts/codex_target_gate_hook.py"
  timeout = 2
  statusMessage = "Kubernetes 분석 대상 확인 중"

  그리고 아래처럼 pre_tool_use가 들어간 state 블록도 삭제한다.

  [hooks.state."/home/daolts/.codex/config.toml:pre_tool_use:0:0"]
  trusted_hash = "sha256:..."

  UserPromptSubmit hook은 필요하면 남겨도 된다. 이번 문제는 PreToolUse가 tool 실행 전 단계에서 막는 것이 핵심이었다.

  ## 자동 수정 방법

  수동 편집이 부담되면 아래를 실행한다.

  python3 - <<'PY'
  from pathlib import Path

  path = Path("/home/daolts/.codex/config.toml")
  text = path.read_text()

  start = text.find("[[hooks.PreToolUse]]")
  if start != -1:
      end = text.find("[[hooks.UserPromptSubmit]]", start)
      if end == -1:
          raise SystemExit("UserPromptSubmit block을 찾지 못했습니다. 수동으로 확인하세요.")
      text = text[:start] + text[end:]

  lines = text.splitlines(keepends=True)
  out = []
  i = 0
  while i < len(lines):
      if "pre_tool_use" in lines[i]:
          i += 1
          while i < len(lines) and not lines[i].lstrip().startswith("["):
              i += 1
          continue
      out.append(lines[i])
      i += 1

  path.write_text("".join(out))
  print("PreToolUse hook disabled:", path)
  PY

  ## 성공 확인

  rg -n "PreToolUse|pre_tool_use" /home/daolts/.codex/config.toml || echo "PreToolUse disabled"

  성공하면 다음처럼 나온다.

  PreToolUse disabled

  ## 적용 방법

  설정을 수정한 뒤에는 현재 Codex 세션을 새로 열어야 한다. 기존 세션은 이미 hook 설정을 읽은 상태라 계속 막힐 수 있다.

  ## 이전 시도에서 실패한 이유

  - .claude/settings.local.json에 PreToolUse: []를 넣어도 Codex 전역 hook에는 적용되지 않았다.
  - 긴 perl 명령을 복사하는 과정에서 줄바꿈이 들어가 정규식이 실제 config 내용과 맞지 않았다.
  - 그래서 명령은 성공 종료했지만 PreToolUse 블록은 남아 있었다.

  ## 복구 방법

  문제가 생기면 백업 파일을 되돌린다.

  cp /home/daolts/.codex/config.toml.bak.YYYYMMDD-HHMMSS.pretooluse-disable /home/daolts/.codex/config.toml

  백업 파일 이름은 실제 생성된 파일명으로 바꿔서 실행한다.

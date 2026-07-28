# MCP `tools/call` Metadata Compatibility Design

## 목표

Qwen Code의 표준 MCP `tools/call` 요청이 `_meta` 또는 task augmentation
필드를 포함해도 report lifecycle server가 호출을 처리하도록 한다.

## 범위

- `name`은 비어 있지 않은 문자열인지 검증한다.
- `arguments`는 기존처럼 JSON object인지 검증하고 report handler에 전달한다.
- MCP 표준 request metadata인 `_meta`와 task augmentation 필드인 `task`는
  허용하지만 report handler에는 전달하지 않는다.
- `name`, `arguments`, `_meta`, `task` 이외의 임의 field는 계속 거부한다.
- 네 report tool 이름, input schema, handler argument, lifecycle 상태 모델은
  변경하지 않는다.

## 처리 흐름

```text
MCP tools/call params
  -> envelope key allowlist 검증
  -> name / arguments 검증
  -> _meta / task 제거
  -> CompleteToolCall(name, arguments)
  -> 기존 ReportToolHandler
```

## 테스트 계약

1. `_meta.progressToken`이 포함된 `report_session_sync` JSON-RPC 호출은
   기존과 같은 handler 결과를 반환한다.
2. `task.ttl`이 포함된 호출도 동일하게 처리된다.
3. 허용되지 않은 field가 포함된 호출은 `-32602`로 거부된다.
4. 기존 initialize, tools/list, 네 tool surface, arguments 전달 테스트는
   계속 통과한다.

## 안전성

메타데이터는 lifecycle business logic에 들어가지 않는다. allowlist 밖의
입력은 계속 거부하므로 Qwen 호환성을 위해 JSON-RPC envelope 검증을
완화하되 tool argument 검증이나 handler surface를 넓히지 않는다.

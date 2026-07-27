# 용어집

## Evidence provenance

Evidence가 수집된 경로를 나타내는 최상위 메타데이터다. 분석 상태(`status`)나
후속 판단의 확실성과는 별개다.

- `EXTRACTED`: 언어별 runtime-signal extractor가 명시적 source construct에서
  수집한 evidence.
- `INFERRED`: universal scanner 또는 evidence pattern pack이 정적 pattern에서
  수집한 evidence.

## Runtime signal

애플리케이션 source에 명시된 Kubernetes 관련 실행 사실이다. 이 저장소에서는
환경/구성 읽기, listener bind, outbound connection 구성, writable filesystem
path, worker·scheduler·background-process 등록만을 뜻한다. Framework default,
dependency declaration, 주석, prose, test-only source는 runtime signal이 아니다.
Test-only source는 `test`, `tests`, `__tests__` 디렉터리 또는 언어 관례의 테스트
파일명에 속하는 source다.

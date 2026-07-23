# Configuration Timing

Classify each major configuration name by when it takes effect.

## 적용 시점 값

- **빌드 시점:** 컴파일, 이미지 생성, 정적 번들 생성 중 포함된다. 바꾸려면 다시 빌드한다.
- **배포 시점:** workload 생성 전 배포 도구가 선택하거나 렌더링한다.
- **프로세스 시작 시점:** 프로세스가 시작할 때 읽는다. 바꾸려면 재시작 또는 rollout이 필요하다.
- **실행 중:** 프로세스가 실행 중일 때 재시작 없이 다시 읽는다.
- **관리 시점:** 외부 제어 plane 또는 수동 관리 작업으로 적용한다.
- **미확인:** 저장소 근거로 적용 시점을 알 수 없다.

## Required Fields

For each important configuration include:

- name
- component
- purpose
- 적용 시점
- source or injection method
- change effect
- secret classification without revealing values
- evidence status

Do not assume every environment variable is process-start configuration. Frontend variables such as Vite build arguments are often build-time settings embedded into static assets.

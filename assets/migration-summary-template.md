# Kubernetes 설계 입력 요약

## 1. 분석 범위

- 대상 유형:
- Repository URL 또는 Local path:
- 접근 방식:
- 확인된 저장소 루트:
- branch, tag 또는 commit:
- 분석 경로:
- 출력 모드: summary

범위와 접근 정보는 분석 metadata이므로 repository line 근거를 붙이지 않는다.

## 2. 배포 대상 후보

- 배포 대상 후보: <이름과 실행 형태 목록> — 상태: <상태> / 근거: <file:line 또는 검색(...)>

## 3. 배포 대상별 실행 정보

배포 대상 후보마다 아래 카드를 반복한다. 이 섹션은 Kubernetes 배포 여부를 확정하지 않고, 저장소에서 확인한 실행 사실만 기록한다.

### 배포 대상: <이름>

#### 실행 정보

- 실행 형태:
- 경로:
- 언어:
- 프레임워크:
- 런타임:
- 패키지 관리자:
- 설치 명령:
- 빌드 명령:
- 이미지 빌드 명령:
- 운영 기동 명령:
- 컨테이너화:
- 프로토콜:
- 수신 포트:
- 상태 확인:

#### 설정과 상태

- 설정:
- Secret:
- 쓰기 상태 또는 영속성:
- 적용 시점:
- 종료와 복구:
- 관찰 가능성:

#### Kubernetes 최소 설계 입력

- workload.kind:
- metadata.name:
- image:
- command:
- args:
- containerPort:
- Service:
- Ingress:

#### 최소 입력 누락

- 없음: 추가 입력 없음 — 상태: 확인됨 / 근거: <file:line 또는 검색(...)>
- <누락 key>: <필요한 이유와 후속 설계 차단 여부> — 상태: <상태> / 근거: <file:line 또는 검색(...)>

## 4. 구성과 관계

### 저장소에 정의된 런타임 의존성: <이름>

- 종류:
- 연결 workload:
- protocol 또는 mechanism:
- endpoint 또는 configuration:
- 실행 위치:
- 기능 실행에 필요:
- 확인된 실행 정의에서 사용 여부:
- 공급 또는 관리 경계: 저장소에 배포 정의 있음 | 외부 관리로 참조 | 미확인
- 상태 또는 영속성:

### 외부 런타임 의존성: <이름>

- 연결 workload:
- protocol 또는 mechanism:
- endpoint 또는 configuration:
- 기능 실행에 필요:
- Secret 또는 identity:

### 배포 대상 후보에서 제외한 항목

- <이름>: <제외 이유> — 상태: <상태> / 근거: <file:line 또는 검색(...)>

## 5. 운영 환경 배포 근거

- 확인된 배포 선언: <Helm, Kustomize, manifest, GitOps 또는 CI release> — 상태: <상태> / 근거: <file:line 또는 검색(...)>
- 저장소에서 확인한 기동 정의: <Compose, script 또는 entrypoint와 포함 서비스> — 상태: <상태> / 근거: <file:line 또는 검색(...)>
- 운영 환경 배포 기준 구성: <확인된 구성 또는 미확인> — 상태: <상태> / 근거: <file:line 또는 검색(...)>

## 6. Kubernetes 설계 입력 상태

이 판정은 후속 Kubernetes 설계에 필요한 저장소 기반 입력의 충분성만 평가한다. production 배포 승인, 보안 승인, SLO 충족을 뜻하지 않는다.

- 판정: 설계 입력 충분 | 추가 정보 필요 | 분석 불가
- 이유:
- 판정을 뒷받침하는 근거:

### 설계 차단 항목

- 차단 항목: <없음 또는 구체적 누락> — 범주: <이미지|Secret|외부 의존성|runtime|기타> / 영향 범위: <전체|특정 배포 대상|production 경로> / 상태: <상태> / 근거: <file:line 또는 검색(...)>

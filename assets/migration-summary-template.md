# Kubernetes 이관 요약

## 1. 범위

- 대상 유형:
- Repository URL 또는 Local path:
- 접근 방식:
- 확인된 저장소 루트:
- branch, tag 또는 commit:
- 분석 경로:
- 출력 모드: summary

범위와 접근 정보는 분석 metadata이므로 임의의 repository line 근거를 붙이지 않는다.

## 2. 한눈에 보기

- 배포 가능한 구성 요소: <이름 목록> — 상태: <상태> / 근거: <file:line>
- 제외한 주요 package: <이름과 제외 이유> — 상태: <상태> / 근거: <file:line>
- 확인된 수신 포트: <구성 요소와 포트 또는 non-listener> — 상태: <상태> / 근거: <file:line>
- 설계를 막는 최소 입력 누락: <없음 또는 값과 이유> — 상태: <상태> / 근거: <file:line 또는 검색(...)>

## 3. 구성 요소별 배포 브리핑

배포 가능한 구성 요소마다 아래 카드를 반복한다. Repository fact에는 `키: 값 — 상태: 확인됨|추정됨|미확인|상충됨 / 근거: <file:line 또는 검색(...)>` 형식을 사용한다. 추정값에는 `/ 판단: <이유>`를 추가한다.

### 구성 요소: <이름>

#### 역할과 실행

- 역할:
- 경로:
- 유형:
- 언어:
- 프레임워크:
- 런타임:

#### 빌드와 기동

- 빌드 명령:
- 운영 기동 명령:
- 컨테이너화:

#### 네트워크와 상태 확인

- 프로토콜:
- 수신 포트:
- 상태 확인:

#### 설정과 상태

- 설정:
- Secret:
- 저장소:
- 볼륨 또는 세션:
- 적용 시점:

#### Kubernetes 최소 설계 입력

저장소 직접 근거는 `확인됨`, 저장소 사실에서 도출한 Kubernetes 후보는 `추정됨`과 판단 이유로 기록한다.

- workload.kind:
- metadata.name:
- image:
- command:
- args:
- containerPort:
- Service:
- Ingress:

#### 최소 입력 누락

- 없음 또는 필수 입력:

## 4. 구성 요소 관계

Summary에서는 관계 카드를 반복하거나 하나의 text dependency graph를 사용한다.

### 관계: <logical source> -> <target>

- dependency type:
- protocol 또는 mechanism:
- endpoint 또는 configuration:
- 시점:
- 실행 위치:
- 필수 여부:

## 5. 최종 판정

- 판정: 준비됨 | 추가 정보 필요 | 진행 불가
- 이유:
- 판정을 뒷받침하는 근거:

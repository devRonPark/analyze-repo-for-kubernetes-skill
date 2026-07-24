from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


VALID_SUMMARY = """# Kubernetes 이관 요약

## 1. 범위
- 대상 유형: Local path
- Local path: /tmp/web
- 접근 방식: read-only local checkout
- 확인된 저장소 루트: /tmp/web
- branch, tag 또는 commit: main@abc123
- 분석 경로: .
- 출력 모드: summary

## 2. 한눈에 보기
- 배포 가능한 구성 요소: web — 상태: 확인됨 / 근거: pom.xml:1
- 기본 배포 구성: web — 상태: 확인됨 / 근거: Dockerfile:1
- 제외한 선택·개발용 구성: 없음 — 상태: 확인됨 / 근거: pom.xml:1
- 제외한 주요 package: 없음 — 상태: 확인됨 / 근거: pom.xml:1
- 확인된 수신 포트: web: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- 적용을 막는 최소 입력 누락: 없음 — 상태: 확인됨 / 근거: pom.xml:1

## 3. 구성 요소별 배포 브리핑

### 구성 요소: web

#### 역할과 실행
- 역할: HTTP 웹 애플리케이션 — 상태: 확인됨 / 근거: pom.xml:1
- 배포 대상 여부: 예 — 상태: 확인됨 / 근거: pom.xml:1
- 배포 구성: default — 상태: 확인됨 / 근거: Dockerfile:1
- 경로: . — 상태: 확인됨 / 근거: pom.xml:1
- 유형: 웹 애플리케이션 — 상태: 확인됨 / 근거: pom.xml:1
- 언어: Java — 상태: 확인됨 / 근거: pom.xml:1
- 프레임워크: Spring — 상태: 확인됨 / 근거: pom.xml:1
- 런타임: Java 17 — 상태: 확인됨 / 근거: pom.xml:1

#### 빌드와 기동
- 패키지 관리자: Maven — 상태: 확인됨 / 근거: pom.xml:1
- 설치 명령: ./mvnw dependency:go-offline — 상태: 추정됨 / 근거: pom.xml:1 / 판단: Maven project dependency resolution 후보
- 빌드 명령: ./mvnw package — 상태: 확인됨 / 근거: pom.xml:1
- 이미지 빌드 명령: docker build -t web . — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: Dockerfile 기반 image build 후보
- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1
- 컨테이너화: 기존 컨테이너 정의 있음 — 상태: 확인됨 / 근거: Dockerfile:1

#### 네트워크와 상태 확인
- 프로토콜: HTTP — 상태: 확인됨 / 근거: Dockerfile:1
- 수신 포트: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- 상태 확인: GET /health — 상태: 확인됨 / 근거: Dockerfile:1

#### 설정과 상태
- 설정: APP_MODE — 상태: 확인됨 / 근거: pom.xml:1
- Secret: 없음 — 상태: 확인됨 / 근거: pom.xml:1
- 저장소: 없음 — 상태: 확인됨 / 근거: pom.xml:1
- 볼륨 또는 세션: 없음 — 상태: 확인됨 / 근거: pom.xml:1
- 적용 시점: 애플리케이션 시작 — 상태: 확인됨 / 근거: pom.xml:1

#### Kubernetes 최소 설계 입력
- workload.kind: Deployment — 상태: 추정됨 / 근거: pom.xml:1 / 판단: 지속 실행 HTTP 서버
- metadata.name: web — 상태: 확인됨 / 근거: pom.xml:1
- image: registry.example/web:1.0 — 상태: 확인됨 / 근거: Dockerfile:1
- command: java — 상태: 확인됨 / 근거: Dockerfile:1
- args: -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1
- containerPort: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- Service: port 8080, targetPort 8080 — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: HTTP listener 노출 후보
- Ingress: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=Ingress|외부 route, result=없음)

#### 최소 입력 누락
- 없음: 확인된 최소 초안 작성에 추가 입력 없음 — 상태: 확인됨 / 근거: Dockerfile:1

## 4. 구성 요소 관계

### 관계: web -> 사용자
- dependency type: HTTP 요청 수신 — 상태: 확인됨 / 근거: Dockerfile:1
- protocol 또는 mechanism: HTTP — 상태: 확인됨 / 근거: Dockerfile:1
- endpoint 또는 configuration: / — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: listener root 후보
- 시점: 요청 처리 — 상태: 추정됨 / 근거: Dockerfile:1
- 실행 위치: 클러스터 내부 Pod — 상태: 추정됨 / 근거: Dockerfile:1
- 애플리케이션 필수 여부: 필수 — 상태: 확인됨 / 근거: Dockerfile:1
- 선택한 배포 구성에서 필요: 필요 — 상태: 확인됨 / 근거: Dockerfile:1

## 5. 최종 판정
- 판정: 준비됨
- 이유: 후속 설계를 차단하는 필수 입력 누락 없음
- 판정을 뒷받침하는 근거: pom.xml:1, Dockerfile:1

### Readiness 차단 요인
- 차단 요인: 없음 — 범주: 기타 / 영향 범위: 전체 / 상태: 확인됨 / 근거: pom.xml:1

### 일반 운영 권장사항
- 권장사항: 없음 — 상태: 확인됨 / 근거: pom.xml:1
"""


NEW_VALID_SUMMARY = """# Kubernetes 설계 입력 요약

## 1. 분석 범위
- 대상 유형: Local path
- Repository URL 또는 Local path: /tmp/web
- 접근 방식: read-only local checkout
- 확인된 저장소 루트: /tmp/web
- branch, tag 또는 commit: main@abc123
- 분석 경로: .
- 출력 모드: summary

## 2. 배포 대상 후보
- 배포 대상 후보: web (HTTP 서버) — 상태: 확인됨 / 근거: Dockerfile:1

## 3. 배포 대상별 실행 정보
### 배포 대상: web
#### 실행 정보
- 실행 형태: HTTP 서버 — 상태: 확인됨 / 근거: Dockerfile:1
- 경로: . — 상태: 확인됨 / 근거: pom.xml:1
- 언어: Java — 상태: 확인됨 / 근거: pom.xml:1
- 프레임워크: Spring — 상태: 확인됨 / 근거: pom.xml:1
- 런타임: Java 17 — 상태: 확인됨 / 근거: pom.xml:1
- 패키지 관리자: Maven — 상태: 확인됨 / 근거: pom.xml:1
- 설치 명령: ./mvnw dependency:go-offline — 상태: 추정됨 / 근거: pom.xml:1 / 판단: Maven 의존성 설치 후보
- 빌드 명령: ./mvnw package — 상태: 확인됨 / 근거: pom.xml:1
- 이미지 빌드 명령: docker build -t web . — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: Dockerfile 기반 후보
- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1
- 컨테이너화: 기존 컨테이너 정의 있음 — 상태: 확인됨 / 근거: Dockerfile:1
- 프로토콜: HTTP — 상태: 확인됨 / 근거: Dockerfile:1
- 수신 포트: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- 상태 확인: GET /health — 상태: 확인됨 / 근거: Dockerfile:1
#### 설정과 상태
- 설정: APP_MODE — 상태: 확인됨 / 근거: pom.xml:1
- Secret: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=SECRET, result=없음)
- 쓰기 상태 또는 영속성: 없음 — 상태: 미확인 / 근거: 검색(scope=., pattern=volume|database, result=없음)
- 적용 시점: 애플리케이션 시작 — 상태: 확인됨 / 근거: pom.xml:1
- 종료와 복구: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=graceful|shutdown|retry, result=없음)
- 관찰 가능성: 상태 확인 endpoint만 확인됨 — 상태: 확인됨 / 근거: Dockerfile:1
#### Kubernetes 최소 설계 입력
- workload.kind: Deployment — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: 지속 HTTP 서버
- metadata.name: web — 상태: 확인됨 / 근거: pom.xml:1
- image: registry.example/web:1.0 — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: 이미지 이름 입력 필요
- command: java — 상태: 확인됨 / 근거: Dockerfile:1
- args: -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1
- containerPort: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- Service: port 8080 — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: HTTP listener 노출 후보
- Ingress: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=Ingress, result=없음)
#### 최소 입력 누락
- 없음: 추가 입력 없음 — 상태: 확인됨 / 근거: Dockerfile:1

## 4. 구성과 관계
### 저장소에 정의된 런타임 의존성: 없음
- 종류: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=postgres|redis|rabbitmq, result=없음)
- 연결 workload: web — 상태: 확인됨 / 근거: Dockerfile:1
- protocol 또는 mechanism: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=postgres|redis|rabbitmq, result=없음)
- endpoint 또는 configuration: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=postgres|redis|rabbitmq, result=없음)
- 실행 위치: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=compose|kustomization, result=없음)
- 기능 실행에 필요: 아니오 — 상태: 확인됨 / 근거: 검색(scope=., pattern=postgres|redis|rabbitmq, result=없음)
- 확인된 실행 정의에서 사용 여부: 아니오 — 상태: 확인됨 / 근거: Dockerfile:1
- 공급 또는 관리 경계: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=compose|kustomization, result=없음)
- 상태 또는 영속성: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=volume|database, result=없음)
### 외부 런타임 의존성: 없음
- 연결 workload: web — 상태: 확인됨 / 근거: Dockerfile:1
- protocol 또는 mechanism: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=https?://, result=없음)
- endpoint 또는 configuration: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=https?://, result=없음)
- 기능 실행에 필요: 아니오 — 상태: 확인됨 / 근거: 검색(scope=., pattern=https?://, result=없음)
- Secret 또는 identity: 없음 — 상태: 확인됨 / 근거: 검색(scope=., pattern=SECRET, result=없음)
### 배포 대상 후보에서 제외한 항목
- 없음: 제외 항목 없음 — 상태: 확인됨 / 근거: pom.xml:1

## 5. 운영 환경 배포 근거
- 확인된 배포 선언: 없음 — 상태: 미확인 / 근거: 검색(scope=., pattern=helm|kustomization|deployment.yaml, result=없음)
- 저장소에서 확인한 기동 정의: Dockerfile CMD — 상태: 확인됨 / 근거: Dockerfile:1
- 운영 환경 배포 기준 구성: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=helm|kustomization|deployment.yaml, result=없음)

## 6. Kubernetes 설계 입력 상태
- 판정: 설계 입력 충분
- 이유: 저장소 기준 실행 정보가 확인됨
- 판정을 뒷받침하는 근거: pom.xml:1, Dockerfile:1
### 설계 차단 항목
- 차단 항목: 없음 — 범주: 기타 / 영향 범위: 전체 / 상태: 확인됨 / 근거: Dockerfile:1
"""


class SkillPackageTests(unittest.TestCase):
    def run_report_validator(
        self,
        report_text: str,
        mode: str = "summary",
        repo_root: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "summary.md"
            report.write_text(report_text, encoding="utf-8")
            command = ["python3", str(ROOT / "scripts/validate_report.py"), str(report), "--mode", mode]
            if repo_root is not None:
                command.extend(["--repo-root", str(repo_root)])
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_package_validator_passes(self):
        result = subprocess.run(
            ["python3", str(ROOT / "scripts/validate_skill.py"), str(ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_target_resolution_gate_contract(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        intake = (ROOT / "references/interview-first-intake.md").read_text(encoding="utf-8")
        combined = skill + "\n" + intake
        for term in [
            "Target Resolution Gate",
            "skill installation directory",
            "repository discovery tool call",
            "Stop the turn after asking",
            "분석 대상 애플리케이션 소스 코드 제공 방식을 알려주세요.",
            "원격 Git URL",
            "로컬 checkout 경로",
            "소스 압축 파일",
            "분석할 원격 Git URL을 알려주세요.",
            "분석할 Local path를 알려주세요.",
            "분석할 소스 압축 파일의 Local path를 알려주세요.",
            "Remote Git URL",
            "Local path",
            "directory listing",
            "tests/",
        ]:
            self.assertIn(term, combined)

    def test_demo_credential_file_contract(self):
        access = (ROOT / "references/remote-git-access.md").read_text(encoding="utf-8")
        example = (ROOT / "assets/demo-git-credential.example.json").read_text(encoding="utf-8")
        for term in [
            "데모용 local credential file 경로 제공",
            "파일 내용이나 Access Token은 대화에 입력하지 마세요.",
            "never opens, searches, quotes or reports the file content",
            "read-only Git request",
            "read_repository",
            '"repository_url"',
            '"access_token"',
        ]:
            self.assertIn(term, access + example)

    def test_demo_credential_file_is_scoped_and_private(self):
        module_path = ROOT / "scripts/demo_git_readonly_clone.py"
        spec = importlib.util.spec_from_file_location("demo_git_readonly_clone", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            credential = Path(tmp) / "credential.json"
            credential.write_text(
                '{"version": 1, "repository_url": "https://git.example.internal/group/project.git", "username": "readonly", "access_token": "demo-token"}',
                encoding="utf-8",
            )
            credential.chmod(0o600)
            loaded = module.load_credential(credential, "https://git.example.internal/group/project.git")
            self.assertEqual(loaded.username, "readonly")
            with self.assertRaises(module.CredentialError):
                module.load_credential(credential, "https://git.example.internal/group/other.git")

    def test_source_intake_uses_stable_ids_and_resolves_local_checkout(self):
        module_path = ROOT / "scripts/source_intake.py"
        spec = importlib.util.spec_from_file_location("source_intake", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertEqual(module.select_source_method("local_checkout")["source_method"], "local_checkout")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            nested = root / "services" / "api"
            nested.mkdir(parents=True)
            for command in [
                ["git", "init", str(root)],
                ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
                ["git", "-C", str(root), "config", "user.name", "Test"],
                ["git", "-C", str(root), "commit", "--allow-empty", "-m", "initial"],
            ]:
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            resolved = module.accept_source_value("local_checkout", str(nested))
            self.assertEqual(resolved["state"], "resolved")
            self.assertEqual(resolved["source_method"], "local_checkout")
            self.assertEqual(resolved["resolved_target"], str(root.resolve()))
            self.assertEqual(resolved["subdirectory"], "services/api")
            with self.assertRaises(module.IntakeError):
                module.accept_source_value("local_checkout", str(root / "missing"))

    def test_output_contract(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                ROOT / "SKILL.md",
                ROOT / "assets/migration-summary-template.md",
                ROOT / "assets/migration-assessment-template.md",
            ]
        )
        for term in [
            "배포 대상별 실행 정보",
            "Kubernetes 최소 설계 입력",
            "최소 입력 누락",
            "키: 값",
            "실행 위치",
            "적용 시점",
            "확인됨",
            "추정됨",
            "미확인",
            "상충됨",
            "설계 입력 충분",
            "추가 정보 필요",
            "분석 불가",
            "path/to/file:line",
        ]:
            self.assertIn(term, text)
        self.assertNotIn("## 다음 작업", text)
        self.assertNotIn("다음 인계:", text)

    def test_fact_based_analysis_outcome_contract(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        summary = (ROOT / "assets/migration-summary-template.md").read_text(encoding="utf-8")
        checklist = (ROOT / "references/repository-analysis-checklist.md").read_text(encoding="utf-8")
        for term in [
            "배포 대상 후보",
            "저장소에 정의된 런타임 의존성",
            "외부 런타임 의존성",
            "배포 대상 후보에서 제외한 항목",
        ]:
            self.assertIn(term, skill + summary + checklist)

    def test_launch_and_operating_environment_evidence_contract(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                ROOT / "SKILL.md",
                ROOT / "references/workflow.md",
                ROOT / "assets/migration-summary-template.md",
            ]
        )
        for term in [
            "저장소에서 확인한 기동 정의",
            "운영 환경 배포 근거",
            "운영 환경 배포 기준 구성",
            "운영 환경의 기준 구성을 단정하지 않는다",
        ]:
            self.assertIn(term, text)

    def test_component_command_inference_contract(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                ROOT / "SKILL.md",
                ROOT / "references/language-discovery-rules.md",
                ROOT / "assets/migration-summary-template.md",
            ]
        )
        for term in [
            "packageManager", "workspace", "lockfile", "Maven", "Gradle",
            "설치 명령", "이미지 빌드 명령", "운영 기동 명령",
        ]:
            self.assertIn(term, text)

    def test_deployment_core_dependency_and_readiness_contract(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                ROOT / "SKILL.md",
                ROOT / "references/workflow.md",
                ROOT / "references/evidence-and-readiness.md",
                ROOT / "assets/migration-summary-template.md",
            ]
        )
        for term in [
            "1차 inventory", "기능 실행에 필요", "공급 또는 관리 경계",
            "설계 차단 항목", "영향 범위", "Kubernetes 설계 입력 상태",
        ]:
            self.assertIn(term, text)

    def test_report_validator_accepts_component_briefing(self):
        result = self.run_report_validator(VALID_SUMMARY)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_accepts_fact_based_summary(self):
        result = self.run_report_validator(NEW_VALID_SUMMARY)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fact_based_summary_rejects_missing_execution_fact(self):
        report = NEW_VALID_SUMMARY.replace("- 종료와 복구: 미확인 — 상태: 미확인 / 근거: 검색(scope=., pattern=graceful|shutdown|retry, result=없음)\n", "")
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("종료와 복구", result.stdout)

    def test_report_validator_accepts_fact_based_detailed_report(self):
        report = NEW_VALID_SUMMARY.replace(
            "# Kubernetes 설계 입력 요약",
            "# Kubernetes 설계 입력 상세 평가",
        ).replace(
            "## 6. Kubernetes 설계 입력 상태",
            "## 6. 설정과 상태 상세\n"
            "- 설정 상세: APP_MODE는 시작 시 적용 — 상태: 확인됨 / 근거: pom.xml:1\n\n"
            "## 7. 제외 항목과 설계 차단 항목 상세\n"
            "- 제외 항목 상세: 없음 — 상태: 확인됨 / 근거: pom.xml:1\n\n"
            "## 8. Kubernetes 설계 입력 상태",
        )
        result = self.run_report_validator(report, mode="detailed")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_rejects_missing_component_property(self):
        report = VALID_SUMMARY.replace("- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1\n", "")
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("운영 기동 명령", result.stdout)

    def test_report_validator_rejects_missing_overview_key(self):
        report = VALID_SUMMARY.replace(
            "- 기본 배포 구성: web — 상태: 확인됨 / 근거: Dockerfile:1\n",
            "",
        )
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("기본 배포 구성", result.stdout)

    def test_report_validator_checks_file_existence_and_line_range_with_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            (repo_root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
            (repo_root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

            result = self.run_report_validator(VALID_SUMMARY, repo_root=repo_root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            missing = self.run_report_validator(
                VALID_SUMMARY.replace("pom.xml:1", "missing.xml:1"), repo_root=repo_root
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("인용 파일", missing.stdout)

            out_of_range = self.run_report_validator(
                VALID_SUMMARY.replace("Dockerfile:1", "Dockerfile:2"), repo_root=repo_root
            )
            self.assertNotEqual(out_of_range.returncode, 0)
            self.assertIn("줄 범위", out_of_range.stdout)

    def test_report_validator_does_not_treat_endpoint_as_file_reference(self):
        report = VALID_SUMMARY.replace(
            "- endpoint 또는 configuration: / — 상태: 추정됨 / 근거: Dockerfile:1 / 판단: listener root 후보",
            "- endpoint 또는 configuration: redis-cart:6379 — 상태: 확인됨 / 근거: Dockerfile:1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            (repo_root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
            (repo_root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            result = self.run_report_validator(report, repo_root=repo_root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_rejects_missing_minimum_value_and_gap(self):
        report = VALID_SUMMARY.replace("- image: registry.example/web:1.0 — 상태: 확인됨 / 근거: Dockerfile:1\n", "")
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("image", result.stdout)

    def test_report_validator_rejects_unkeyed_minimum_input_gap(self):
        report = VALID_SUMMARY.replace(
            "- 없음: 확인된 최소 초안 작성에 추가 입력 없음 — 상태: 확인됨 / 근거: Dockerfile:1",
            "- 없음 — 상태: 확인됨 / 근거: Dockerfile:1",
        )
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("key: value", result.stdout)

    def test_report_validator_rejects_property_without_file_line_evidence(self):
        report = VALID_SUMMARY.replace(
            "- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1",
            "- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile",
        )
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("file:line 또는 검색(...)", result.stdout)

    def test_report_validator_accepts_absence_search_evidence(self):
        result = self.run_report_validator(VALID_SUMMARY)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_accepts_markdown_wrapped_file_line_evidence(self):
        report = VALID_SUMMARY.replace(
            "근거: Dockerfile:1",
            "근거: `Dockerfile:1`",
        )
        result = self.run_report_validator(report)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_accepts_dynamic_route_file_reference(self):
        report = VALID_SUMMARY.replace("Dockerfile:1", "pages/[id].tsx:1")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            (repo_root / "pages").mkdir(parents=True)
            (repo_root / "pages/[id].tsx").write_text("export default null\n", encoding="utf-8")
            (repo_root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
            result = self.run_report_validator(report, repo_root=repo_root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_rejects_unstructured_absence_claim(self):
        report = VALID_SUMMARY.replace(
            "검색(scope=., pattern=Ingress|외부 route, result=없음)",
            "저장소에서 찾지 못함",
        )
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("file:line 또는 검색(...)", result.stdout)

    def test_detailed_report_requires_matrix_and_graph(self):
        report = VALID_SUMMARY.replace(
            "# Kubernetes 이관 요약",
            "# Kubernetes 이관 상세 평가",
        ).replace(
            "## 1. 범위",
            "## 1. 평가 범위",
        ).replace(
            "## 5. 최종 판정",
            "## 5. 설정과 상태 상세\n\n- 설정: APP_MODE — 상태: 확인됨 / 근거: pom.xml:1\n\n"
            "## 6. 최소 입력 누락과 conflict 상세\n\n"
            "- 누락: 없음 — 상태: 확인됨 / 근거: pom.xml:1\n\n"
            "## 7. 최종 판정",
        )
        result = self.run_report_validator(report, mode="detailed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Dependency matrix", result.stdout)
        self.assertIn("Text dependency graph", result.stdout)

    def test_detailed_report_accepts_matrix_and_graph(self):
        report = VALID_SUMMARY.replace(
            "# Kubernetes 이관 요약",
            "# Kubernetes 이관 상세 평가",
        ).replace(
            "## 1. 범위",
            "## 1. 평가 범위",
        ).replace(
            "## 4. 구성 요소 관계",
            "## 4. 구성 요소 관계\n\n"
            "### Dependency matrix\n\n"
            "| Source | Target | 근거 |\n"
            "|---|---|---|\n"
            "| web | 사용자 | Dockerfile:1 |\n\n"
            "### Text dependency graph\n\n"
            "web --[HTTP]--> 사용자\n",
        ).replace(
            "## 5. 최종 판정",
            "## 5. 설정과 상태 상세\n\n- 설정: APP_MODE — 상태: 확인됨 / 근거: pom.xml:1\n\n"
            "## 6. 최소 입력 누락과 conflict 상세\n\n"
            "- 누락: 없음 — 상태: 확인됨 / 근거: pom.xml:1\n\n"
            "## 7. 최종 판정",
        )
        result = self.run_report_validator(report, mode="detailed")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_rejects_next_action_section(self):
        report = VALID_SUMMARY + "\n## 다음 작업\n- 작업: 배포\n"
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("작업 계획", result.stdout)

    def test_fixed_output_regression_fixture_is_deterministic(self):
        fixture = ROOT / "tests/fixtures/regression/expected.json"
        result = subprocess.run(
            ["python3", str(ROOT / "scripts/validate_regression.py"), str(fixture)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_known_actual_output_schema_regression_fails(self):
        fixture = ROOT / "tests/fixtures/regression/invalid-actual-output.md"
        result = subprocess.run(
            ["python3", str(ROOT / "scripts/validate_report.py"), str(fixture)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("필수 키", result.stdout)


if __name__ == "__main__":
    unittest.main()

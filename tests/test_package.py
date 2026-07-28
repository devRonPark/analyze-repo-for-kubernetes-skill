from pathlib import Path
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
import importlib.util
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/analyze-repo-for-kubernetes"
PLUGIN_SKILL = SKILL_ROOT / "SKILL.md"


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
    def test_package_requires_report_contract_artifact(self):
        validator = (ROOT / "scripts/validate_plugin_package.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"contracts/report-contract-v1.json"', validator)

    def test_plugin_owns_one_nested_skill(self):
        self.assertTrue(PLUGIN_SKILL.is_file())
        self.assertFalse((ROOT / "SKILL.md").exists())
        self.assertFalse((ROOT / "agents/openai.yaml").exists())
        self.assertTrue(
            (ROOT / "skills/analyze-repo-for-kubernetes/agents/openai.yaml").is_file()
        )
        self.assertEqual(
            [PLUGIN_SKILL],
            [
                path
                for path in ROOT.rglob("*")
                if path.is_file() and path.name.lower() == "skill.md"
            ],
        )

    def test_plugin_manifest_exposes_nested_skill_directory(self):
        manifest_path = ROOT / ".codex-plugin/plugin.json"
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "analyze-repo-for-kubernetes")
        self.assertEqual(manifest["skills"], "./skills/")

    def run_report_validator(
        self,
        report_text: str,
        mode: str = "summary",
        repo_root: Path | None = None,
        contract: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "summary.md"
            report.write_text(report_text, encoding="utf-8")
            command = ["python3", str(ROOT / "scripts/validate_report.py"), str(report), "--mode", mode]
            if contract is not None:
                command.extend(["--contract", contract])
            if repo_root is not None:
                command.extend(["--repo-root", str(repo_root)])
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )

    def fact_based_detailed_report(self) -> str:
        return NEW_VALID_SUMMARY.replace(
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

    def strip_h2_numbers(self, report: str) -> str:
        return "\n".join(
            line.replace("## 1. ", "## ")
            .replace("## 2. ", "## ")
            .replace("## 3. ", "## ")
            .replace("## 4. ", "## ")
            .replace("## 5. ", "## ")
            .replace("## 6. ", "## ")
            .replace("## 7. ", "## ")
            .replace("## 8. ", "## ")
            for line in report.splitlines()
        )

    def test_package_validator_passes(self):
        result = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/validate_plugin_package.py"),
                str(ROOT),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_skill_entrypoint_stays_small_and_routes_details_progressively(self):
        skill = PLUGIN_SKILL.read_text(encoding="utf-8")
        body = skill.split("---", 2)[2]
        self.assertLessEqual(len(body.splitlines()), 90)
        for reference in [
            "references/interview-first-intake.md",
            "references/workflow.md",
            "references/repository-analysis-checklist.md",
            "references/dependency-analysis.md",
            "references/evidence-and-readiness.md",
            "assets/migration-summary-template.md",
            "assets/migration-assessment-template.md",
        ]:
            self.assertIn(reference, skill)
        self.assertIn("<plugin-root>/scripts/prepare_analysis_target.py", skill)
        self.assertIn("두 단계 상위", skill)

    def test_github_actions_runs_cli_independent_core_suite(self):
        workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
        self.assertIn(
            "PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v",
            workflow,
        )

    def test_target_resolution_gate_contract(self):
        skill = PLUGIN_SKILL.read_text(encoding="utf-8")
        intake = (SKILL_ROOT / "references/interview-first-intake.md").read_text(encoding="utf-8")
        state = (SKILL_ROOT / "references/source-intake-state.md").read_text(encoding="utf-8")
        combined = skill + "\n" + intake + "\n" + state
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
            "Source archive",
            "Slash Command Input",
            "ZIP, tar, tar.gz, tgz",
            "directory listing",
            "tests/",
        ]:
            self.assertIn(term, combined)

    def test_targetless_slash_command_uses_two_step_ask_user_question(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                PLUGIN_SKILL,
                SKILL_ROOT / "references/source-intake-state.md",
                SKILL_ROOT / "references/interview-first-intake.md",
                ROOT / "tests/scenarios.md",
            ]
        )
        for term in [
            "source_method_required",
            "target_value_required",
            "request_user_input",
            "분석 대상 애플리케이션 소스 코드 제공 방식을 알려주세요.",
            "remote_git",
            "local_checkout",
            "source_archive",
            "Repository URL",
            "Source archive",
            "분석할 원격 Git URL을 알려주세요.",
            "분석할 Local path를 알려주세요.",
            "분석할 소스 압축 파일의 Local path를 알려주세요.",
            "first source-method question and second target-value question never occur in the same turn",
        ]:
            self.assertIn(term, text)
        self.assertNotIn("분석할 Git URL, Local path 또는 Source archive를 알려 주세요.", text)

    def test_resolved_analysis_request_contract(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                PLUGIN_SKILL,
                SKILL_ROOT / "references/source-intake-state.md",
                SKILL_ROOT / "references/workflow.md",
            ]
        )
        for term in [
            "ResolvedAnalysisRequest",
            "source_method_required",
            "target_value_required",
            "purpose_required",
            "analysis_ready",
            "intent",
            "scope",
            "focus",
            "output_mode",
            "provider",
            "phase",
            "빠른 구조 파악",
            "Kubernetes 설계 준비",
            "이관 문제점 점검",
            "전체 상세 보고서",
            "기본 분석으로 진행",
            "source-method, target-value and purpose questions never occur in the same turn",
            "Never ask the user to select `summary`, `detailed`, `provider` or `phase`",
        ]:
            self.assertIn(term, text)

    def test_codex_target_gate_hook_contract(self):
        hook = (ROOT / "scripts/codex_target_gate_hook.py").read_text(encoding="utf-8")
        manifest = (ROOT / "hooks.json").read_text(encoding="utf-8")
        state = (SKILL_ROOT / "references/source-intake-state.md").read_text(encoding="utf-8")
        for term in [
            "PreToolUse",
            "source_method_required",
            "target_value_required",
            "purpose_required",
            "analysis_ready",
            "permissionDecision",
            "Source 제공 방식 확정 전에는 repository discovery tool을 사용할 수 없습니다",
            "Target 값 확정 전에는 repository discovery tool을 사용할 수 없습니다",
            "bootstrap read",
        ]:
            self.assertIn(term, hook + manifest + state)

    def test_opt_in_codex_cli_validator_contract(self):
        validator = (ROOT / "scripts/validate_codex_intake.py").read_text(encoding="utf-8")
        runbook = (SKILL_ROOT / "references/codex-ui-integration.md").read_text(encoding="utf-8")
        for term in [
            "CODEX_INTEGRATION",
            "--ephemeral",
            "--sandbox",
            "projectless ASCII task",
            "workspace 탐색 command 없음",
        ]:
            self.assertIn(term, validator + runbook)

    def test_user_facing_invocation_examples_hide_internal_choices(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        prompt = (SKILL_ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
        execution = readme.split("## 실행", 1)[1].split("## 결과 검사", 1)[0]

        for term in [
            "/analyze-repo-for-kubernetes",
            "GitHub URL이 포함된 자연어 요청",
            "https://github.com/example/payments-service.git",
            "/workspace/payments-service",
            "/downloads/payments-service.tar.gz",
            "빠른 구조 파악",
            "Kubernetes 설계 준비",
            "이관 문제점 점검",
            "전체 상세 보고서",
            "기본 분석으로 진행",
        ]:
            self.assertIn(term, execution)

        self.assertNotIn("summary 모드", execution)
        self.assertNotIn("detailed 모드", execution)
        self.assertNotIn("summary mode", prompt)
        self.assertNotIn("detailed mode", prompt)

    def test_demo_credential_file_contract(self):
        access = (SKILL_ROOT / "references/remote-git-access.md").read_text(encoding="utf-8")
        example = (SKILL_ROOT / "assets/demo-git-credential.example.json").read_text(encoding="utf-8")
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

    def test_plain_remote_clone_rejects_embedded_credentials_and_uses_no_credential_option(self):
        module_path = ROOT / "scripts/plain_remote_git_clone.py"
        spec = importlib.util.spec_from_file_location("plain_remote_git_clone", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertEqual(module.validate_remote_url("https://github.com/example/project.git"), "https")
        self.assertEqual(module.validate_remote_url("git@github.com:example/project.git"), "ssh")
        with self.assertRaises(module.CloneError):
            module.validate_remote_url("https://token@github.com/example/project.git")
        command = module.plain_clone_command("https://github.com/example/project.git", Path("/tmp/disposable-clone"))
        self.assertEqual(command[:3], ["git", "clone", "--quiet"])
        self.assertNotIn("credential.helper", " ".join(command))
        self.assertNotIn("credential-file", " ".join(command))

    def test_remote_git_auth_branches_by_protocol_without_collecting_secrets(self):
        module_path = ROOT / "scripts/remote_git_auth.py"
        spec = importlib.util.spec_from_file_location("remote_git_auth", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        https = module.authentication_options("https://git.example.internal/group/project.git")
        self.assertEqual(https["remote_scheme"], "https")
        self.assertEqual(
            [item["id"] for item in https["auth_methods"]],
            ["existing_git_auth", "demo_credential_file", "alternate_source"],
        )
        self.assertEqual(
            module.accept_authentication_method(
                "https://git.example.internal/group/project.git", "demo_credential_file"
            )["state"],
            "awaiting_credential_file",
        )

        ssh = module.authentication_options("git@git.example.internal:group/project.git")
        self.assertEqual(ssh["remote_scheme"], "ssh")
        self.assertTrue(ssh["next_prompt"].startswith("SSH 원격 Git 저장소"))
        self.assertEqual([item["id"] for item in ssh["auth_methods"]], ["ssh_agent", "alternate_source"])
        with self.assertRaises(module.AuthenticationError):
            module.accept_authentication_method("ssh://git@git.example.internal/group/project.git", "demo_credential_file")
        self.assertEqual(
            module.accept_authentication_method("ssh://git@git.example.internal/group/project.git", "ssh_agent"),
            {
                "state": "retry_plain_clone",
                "remote_scheme": "ssh",
                "auth_method": "ssh_agent",
                "next_action": "plain_remote_git_clone",
            },
        )

    def test_source_archive_extracts_safe_content_and_rejects_unsafe_members(self):
        module_path = ROOT / "scripts/source_archive.py"
        spec = importlib.util.spec_from_file_location("source_archive", module_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "source.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("service/app.py", "print('safe')\n")
            resolved = module.extract_source_archive(archive, root / "extracted")
            self.assertEqual(resolved["state"], "resolved")
            self.assertEqual(resolved["subdirectory"], "service")
            self.assertTrue((Path(resolved["resolved_target"]) / "app.py").is_file())
            self.assertTrue(resolved["revision"].startswith("archive-sha256:"))

            multiple = root / "multiple.zip"
            with zipfile.ZipFile(multiple, "w") as zipped:
                zipped.writestr("api/app.py", "")
                zipped.writestr("web/app.py", "")
            ambiguous = module.extract_source_archive(multiple, root / "multiple-extracted")
            self.assertEqual(ambiguous["state"], "awaiting_subdirectory")
            self.assertEqual(ambiguous["candidate_subdirectories"], ["api", "web"])

            traversal = root / "traversal.zip"
            with zipfile.ZipFile(traversal, "w") as zipped:
                zipped.writestr("../outside.txt", "unsafe")
            with self.assertRaises(module.ArchiveError):
                module.extract_source_archive(traversal, root / "traversal-extracted")

            link = root / "link.tar.gz"
            with tarfile.open(link, "w:gz") as tarred:
                member = tarfile.TarInfo("service/link")
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                tarred.addfile(member)
            with self.assertRaises(module.ArchiveError):
                module.extract_source_archive(link, root / "link-extracted")

    def test_output_contract(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                PLUGIN_SKILL,
                SKILL_ROOT / "assets/migration-summary-template.md",
                SKILL_ROOT / "assets/migration-assessment-template.md",
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
        skill = PLUGIN_SKILL.read_text(encoding="utf-8")
        summary = (SKILL_ROOT / "assets/migration-summary-template.md").read_text(encoding="utf-8")
        checklist = (SKILL_ROOT / "references/repository-analysis-checklist.md").read_text(encoding="utf-8")
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
                PLUGIN_SKILL,
                SKILL_ROOT / "references/workflow.md",
                SKILL_ROOT / "assets/migration-summary-template.md",
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
                PLUGIN_SKILL,
                SKILL_ROOT / "references/language-discovery-rules.md",
                SKILL_ROOT / "assets/migration-summary-template.md",
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
                PLUGIN_SKILL,
                SKILL_ROOT / "references/workflow.md",
                SKILL_ROOT / "references/evidence-and-readiness.md",
                SKILL_ROOT / "assets/migration-summary-template.md",
            ]
        )
        for term in [
            "1차 inventory", "기능 실행에 필요", "공급 또는 관리 경계",
            "설계 차단 항목", "영향 범위", "Kubernetes 설계 입력 상태",
        ]:
            self.assertIn(term, text)

    def test_adr_records_evidence_patterns_as_collection_rules(self):
        adr = ROOT / "ADR.md"
        self.assertTrue(adr.is_file(), "ADR.md")
        text = adr.read_text(encoding="utf-8")
        for term in [
            "# 근거 패턴은 판단 규칙이 아니라 수집 규칙으로 사용한다",
            "상태: accepted",
            "line-addressable typed evidence",
            "production readiness",
            "deployable ownership",
            "default deployment path",
            "requiredness",
            "LLM-centered triage",
            "deterministic verifier",
            "unsupported claim",
            "invalid citation",
            "schema drift",
            "secret leakage",
            "maintained pattern",
        ]:
            self.assertIn(term, text)

    def test_evidence_pattern_packs_reference_contract(self):
        reference = SKILL_ROOT / "references/evidence-pattern-packs.md"
        self.assertTrue(reference.is_file(), "references/evidence-pattern-packs.md")
        text = reference.read_text(encoding="utf-8")
        for term in [
            "# Evidence Pattern Packs",
            "Universal scanner",
            "Docker",
            "Compose",
            "Kubernetes",
            "Helm",
            "Kustomize",
            "GitHub Actions",
            "Java",
            "Node",
            "Python",
            "Go",
            ".NET",
            "Ruby/Rails",
            "PHP/Laravel",
            "Rust",
            "Procfile",
            "fly.toml",
            "render.yaml",
            "railway.toml",
            "Cloud Foundry",
            "Serverless",
            "Nx",
            "Turbo",
            "Makefile",
            "Taskfile",
            "LLM-discovered hint 승격 기준",
            "근거 수집",
            "판단하지 않는다",
        ]:
            self.assertIn(term, text)

    def test_evidence_collection_pipeline_contract(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                PLUGIN_SKILL,
                SKILL_ROOT / "references/workflow.md",
                SKILL_ROOT / "references/evidence-pattern-packs.md",
            ]
        )
        for term in [
            "Universal Scanner -> Evidence Pattern Packs -> LLM Triage/Reasoning -> Deterministic Verifier -> Report",
            "deterministic collection",
            "evidence만",
            "component decision",
            "LLM triage",
            "schema",
            "citation validity",
            "최종 방어선",
            "package manifest",
            "dependency",
            "script",
            "Docker/Compose",
            "CI job",
            "candidate evidence",
            "추정됨",
            "미확인",
            "상충됨",
        ]:
            self.assertIn(term, text)

    def test_new_scenarios_cover_evidence_pattern_edge_cases(self):
        scenarios = (ROOT / "tests/scenarios.md").read_text(encoding="utf-8")
        for term in [
            "Dockerfile은 없지만 app evidence가 충분한 경우",
            "package manifest는 있지만 deployable runtime이 없는 경우",
            "Compose service가 production baseline이 아니라 local support인 경우",
            "monorepo에서 workspace/package-manager conflict가 있는 경우",
            "verifier가 invalid citation을 잡는 경우",
        ]:
            self.assertIn(term, scenarios)

    def test_report_validator_accepts_component_briefing(self):
        result = self.run_report_validator(VALID_SUMMARY, contract="legacy")
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
        report = self.fact_based_detailed_report()
        result = self.run_report_validator(report, mode="detailed")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_accepts_fact_based_detailed_report_without_numbered_headings(self):
        report = self.strip_h2_numbers(self.fact_based_detailed_report())
        result = self.run_report_validator(report, mode="detailed")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("계약: NEW_DETAILED", result.stdout)
        self.assertIn("경고: 섹션 번호 접두사가 없습니다: ## 1. 분석 범위", result.stdout)

    def test_report_validator_ignores_adversarial_new_contract_heading_inside_code_block(self):
        report = (
            "# Kubernetes 설계 입력 상세 평가\n\n"
            "```markdown\n"
            "## 3. 배포 대상별 실행 정보\n"
            "```\n\n"
            "- 판정: 추가 정보 필요\n"
            "- 근거: Dockerfile:1\n"
        )
        result = self.run_report_validator(report, mode="detailed")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith("실패: 보고서 계약을 감지할 수 없습니다"), result.stdout)
        self.assertNotIn("평가 범위", result.stdout)

    def test_report_validator_rejects_missing_component_property(self):
        report = VALID_SUMMARY.replace("- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1\n", "")
        result = self.run_report_validator(report, contract="legacy")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("운영 기동 명령", result.stdout)

    def test_report_validator_rejects_missing_overview_key(self):
        report = VALID_SUMMARY.replace(
            "- 기본 배포 구성: web — 상태: 확인됨 / 근거: Dockerfile:1\n",
            "",
        )
        result = self.run_report_validator(report, contract="legacy")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("기본 배포 구성", result.stdout)

    def test_report_validator_checks_file_existence_and_line_range_with_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            (repo_root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
            (repo_root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

            result = self.run_report_validator(VALID_SUMMARY, repo_root=repo_root, contract="legacy")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            missing = self.run_report_validator(
                VALID_SUMMARY.replace("pom.xml:1", "missing.xml:1"), repo_root=repo_root, contract="legacy"
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("인용 파일", missing.stdout)

            out_of_range = self.run_report_validator(
                VALID_SUMMARY.replace("Dockerfile:1", "Dockerfile:2"), repo_root=repo_root, contract="legacy"
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
            result = self.run_report_validator(report, repo_root=repo_root, contract="legacy")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_rejects_missing_minimum_value_and_gap(self):
        report = VALID_SUMMARY.replace("- image: registry.example/web:1.0 — 상태: 확인됨 / 근거: Dockerfile:1\n", "")
        result = self.run_report_validator(report, contract="legacy")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("image", result.stdout)

    def test_report_validator_rejects_unkeyed_minimum_input_gap(self):
        report = VALID_SUMMARY.replace(
            "- 없음: 확인된 최소 초안 작성에 추가 입력 없음 — 상태: 확인됨 / 근거: Dockerfile:1",
            "- 없음 — 상태: 확인됨 / 근거: Dockerfile:1",
        )
        result = self.run_report_validator(report, contract="legacy")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("key: value", result.stdout)

    def test_report_validator_rejects_property_without_file_line_evidence(self):
        report = VALID_SUMMARY.replace(
            "- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1",
            "- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile",
        )
        result = self.run_report_validator(report, contract="legacy")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("file:line 또는 검색(...)", result.stdout)

    def test_report_validator_accepts_absence_search_evidence(self):
        result = self.run_report_validator(VALID_SUMMARY, contract="legacy")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_accepts_markdown_wrapped_file_line_evidence(self):
        report = VALID_SUMMARY.replace(
            "근거: Dockerfile:1",
            "근거: `Dockerfile:1`",
        )
        result = self.run_report_validator(report, contract="legacy")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_accepts_dynamic_route_file_reference(self):
        report = VALID_SUMMARY.replace("Dockerfile:1", "pages/[id].tsx:1")
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            (repo_root / "pages").mkdir(parents=True)
            (repo_root / "pages/[id].tsx").write_text("export default null\n", encoding="utf-8")
            (repo_root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
            result = self.run_report_validator(report, repo_root=repo_root, contract="legacy")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_rejects_unstructured_absence_claim(self):
        report = VALID_SUMMARY.replace(
            "검색(scope=., pattern=Ingress|외부 route, result=없음)",
            "저장소에서 찾지 못함",
        )
        result = self.run_report_validator(report, contract="legacy")
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
        result = self.run_report_validator(report, mode="detailed", contract="legacy")
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
        result = self.run_report_validator(report, mode="detailed", contract="legacy")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_rejects_next_action_section(self):
        report = VALID_SUMMARY + "\n## 다음 작업\n- 작업: 배포\n"
        result = self.run_report_validator(report, contract="legacy")
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
        self.assertIn("보고서 계약을 감지할 수 없습니다", result.stdout)
        self.assertNotIn("평가 범위", result.stdout)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


VALID_SUMMARY = """# Kubernetes 이관 요약

## 1. 범위
- 대상: web 저장소 — 상태: 확인됨 / 근거: pom.xml:1

## 2. 한눈에 보기
- 배포 가능한 구성 요소: web — 상태: 확인됨 / 근거: pom.xml:1
- 확인된 수신 포트: web: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- 적용을 막는 최소 입력 누락: 없음 — 상태: 확인됨 / 근거: pom.xml:1
- 현재 판정: 준비됨 — 상태: 확인됨 / 근거: pom.xml:1

## 3. 구성 요소별 배포 브리핑

### 구성 요소: web

#### 역할과 실행
- 역할: HTTP 웹 애플리케이션 — 상태: 확인됨 / 근거: pom.xml:1
- 경로: . — 상태: 확인됨 / 근거: pom.xml:1
- 유형: 웹 애플리케이션 — 상태: 확인됨 / 근거: pom.xml:1
- 언어: Java — 상태: 확인됨 / 근거: pom.xml:1
- 프레임워크: Spring — 상태: 확인됨 / 근거: pom.xml:1
- 런타임: Java 17 — 상태: 확인됨 / 근거: pom.xml:1

#### 빌드와 기동
- 빌드 명령: ./mvnw package — 상태: 확인됨 / 근거: pom.xml:1
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

#### Kubernetes 최소 초안
- workload.kind: Deployment — 상태: 추정됨 / 근거: pom.xml:1
- metadata.name: web — 상태: 확인됨 / 근거: pom.xml:1
- image: registry.example/web:1.0 — 상태: 확인됨 / 근거: Dockerfile:1
- command: java — 상태: 확인됨 / 근거: Dockerfile:1
- args: -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1
- containerPort: 8080 — 상태: 확인됨 / 근거: Dockerfile:1
- Service: port 8080, targetPort 8080 — 상태: 추정됨 / 근거: Dockerfile:1
- Ingress: 해당 없음 — 상태: 미확인 / 근거: Dockerfile:1

#### 최소 입력 누락
- 없음: 확인된 최소 초안 작성에 추가 입력 없음 — 상태: 확인됨 / 근거: Dockerfile:1

## 4. 구성 요소 관계

### 관계: web -> 사용자
- 연결 방식: HTTP 요청 수신 — 상태: 확인됨 / 근거: Dockerfile:1
- 시점: 요청 처리 — 상태: 추정됨 / 근거: Dockerfile:1
- 실행 위치: 클러스터 내부 Pod — 상태: 추정됨 / 근거: Dockerfile:1
- 필수 여부: 필수 — 상태: 확인됨 / 근거: Dockerfile:1

## 5. 최종 판정
- 판정: 준비됨 — 상태: 확인됨 / 근거: pom.xml:1
"""


class SkillPackageTests(unittest.TestCase):
    def run_report_validator(self, report_text: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "summary.md"
            report.write_text(report_text, encoding="utf-8")
            return subprocess.run(
                ["python3", str(ROOT / "scripts/validate_report.py"), str(report), "--mode", "summary"],
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
            "skill installation directory is not the analysis target",
            "before any repository discovery tool call",
            "stop the turn after asking",
            "Repository URL",
            "Local path",
            "list_directory",
            "read_file",
            "tests/fixtures",
        ]:
            self.assertIn(term, combined)

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
            "구성 요소별 배포 브리핑",
            "Kubernetes 최소 초안",
            "최소 입력 누락",
            "키: 값",
            "실행 위치",
            "적용 시점",
            "확인됨",
            "추정됨",
            "미확인",
            "상충됨",
            "준비됨",
            "추가 정보 필요",
            "진행 불가",
            "path/to/file:line",
        ]:
            self.assertIn(term, text)
        self.assertNotIn("## 다음 작업", text)
        self.assertNotIn("다음 인계:", text)

    def test_report_validator_accepts_component_briefing(self):
        result = self.run_report_validator(VALID_SUMMARY)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_validator_rejects_missing_component_property(self):
        report = VALID_SUMMARY.replace("- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1\n", "")
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("운영 기동 명령", result.stdout)

    def test_report_validator_rejects_missing_minimum_value_and_gap(self):
        report = VALID_SUMMARY.replace("- image: registry.example/web:1.0 — 상태: 확인됨 / 근거: Dockerfile:1\n", "")
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("image", result.stdout)

    def test_report_validator_rejects_property_without_file_line_evidence(self):
        report = VALID_SUMMARY.replace(
            "- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile:1",
            "- 운영 기동 명령: java -jar app.jar — 상태: 확인됨 / 근거: Dockerfile",
        )
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("file:line", result.stdout)

    def test_report_validator_rejects_next_action_section(self):
        report = VALID_SUMMARY + "\n## 다음 작업\n- 작업: 배포\n"
        result = self.run_report_validator(report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("작업 계획", result.stdout)


if __name__ == "__main__":
    unittest.main()

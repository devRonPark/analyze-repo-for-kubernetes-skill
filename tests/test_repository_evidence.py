from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repository_evidence.py"
VALIDATOR = ROOT / "scripts" / "validate_repository_evidence.py"


class RepositoryEvidenceTests(unittest.TestCase):
    def run_collector(self, repository: Path, *extra: str) -> dict:
        result = subprocess.run(
            ["python3", str(SCRIPT), str(repository), *extra],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def run_collector_process(self, repository: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT), str(repository), *extra],
            capture_output=True,
            text=True,
            check=False,
        )

    def run_validator(self, payload: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "repository-evidence.json"
            artifact.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return subprocess.run(
                ["python3", str(VALIDATOR), str(artifact)],
                capture_output=True,
                text=True,
                check=False,
            )

    def assert_validator_rejects(self, payload: dict, code: str) -> None:
        result = self.run_validator(payload)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail("validator did not emit machine-readable JSON: " + result.stdout + result.stderr)
        self.assertFalse(response["valid"])
        self.assertIn(code, {error["code"] for error in response["errors"]})

    def test_collector_emits_stable_schema_identity_source_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "package.json").write_text(
                '{"scripts":{"start":"node src/server.js"},"packageManager":"pnpm@9"}\n',
                encoding="utf-8",
            )
            src = repo / "src"
            src.mkdir()
            (src / "server.js").write_text(
                "const http = require('http')\n"
                "server.listen(process.env.PORT || 3000)\n",
                encoding="utf-8",
            )

            first = self.run_collector_process(repo)
            second = self.run_collector_process(repo)

        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        self.assertEqual(first.stdout, second.stdout)

        payload = json.loads(first.stdout)
        self.assertEqual(payload["schema_version"], "repository-evidence/v1")
        ids = [item["id"] for item in payload["evidence"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(any(identifier.startswith("ev-000") for identifier in ids))

        line_counts = {entry["path"]: entry["line_count"] for entry in payload["snapshot"]["files"]}
        positive_items = [item for item in payload["evidence"] if item["kind"] != "absence"]
        self.assertTrue(positive_items)
        for item in positive_items:
            source = item["source"]
            self.assertIn(source["path"], line_counts)
            self.assertGreaterEqual(source["start_line"], 1)
            self.assertGreaterEqual(source["end_line"], source["start_line"])
            self.assertLessEqual(source["end_line"], line_counts[source["path"]])
            self.assertEqual(item["evidence"], f"{source['path']}:{source['start_line']}")
            self.assertEqual(item["extractor"]["name"], "repository_evidence")
            self.assertRegex(item["extractor"]["version"], r"^\d+\.\d+\.\d+$")

        absence = next(item for item in payload["evidence"] if item["kind"] == "absence")
        self.assertNotIn("source", absence)
        self.assertEqual(absence["absence"], {"scope": ".", "pattern": "Dockerfile|Containerfile", "result": "없음"})

        validation = self.run_validator(payload)
        self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)
        self.assertEqual(json.loads(validation.stdout), {"valid": True, "errors": []})

    def test_validator_rejects_malformed_repository_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "package.json").write_text('{"scripts":{"start":"node server.js"}}\n', encoding="utf-8")
            (repo / "server.js").write_text("app.listen(3000)\n", encoding="utf-8")
            payload = self.run_collector(repo)

        duplicate = json.loads(json.dumps(payload))
        duplicate["evidence"][1]["id"] = duplicate["evidence"][0]["id"]
        self.assert_validator_rejects(duplicate, "duplicate_id")

        positive_index = next(index for index, item in enumerate(payload["evidence"]) if item["kind"] != "absence")

        invalid_span = json.loads(json.dumps(payload))
        invalid_span["evidence"][positive_index]["source"]["end_line"] = 999
        self.assert_validator_rejects(invalid_span, "source_span_out_of_bounds")

        escaped_path = json.loads(json.dumps(payload))
        escaped_path["evidence"][positive_index]["source"]["path"] = "../secrets.env"
        self.assert_validator_rejects(escaped_path, "repository_root_escape")

        unknown_kind = json.loads(json.dumps(payload))
        unknown_kind["evidence"][positive_index]["kind"] = "llm_readiness_decision"
        self.assert_validator_rejects(unknown_kind, "unknown_evidence_kind")

        leaked_secret = json.loads(json.dumps(payload))
        leaked_secret["evidence"][positive_index]["data"]["snippet"] = "API_TOKEN=raw-secret-value"
        self.assert_validator_rejects(leaked_secret, "secret_value_leak")

    def test_validator_accepts_current_legacy_evidence_shape(self):
        legacy = {
            "schema_version": 1,
            "snapshot": {
                "repository_root": "/tmp/repo",
                "analysis_root": "/tmp/repo",
                "subdirectory": ".",
                "revision": None,
                "files": [
                    {"path": "package.json", "size_bytes": 42, "extension": ".json", "line_count": 1},
                ],
            },
            "evidence": [
                {
                    "id": "ev-0001",
                    "kind": "manifest",
                    "status": "confirmed",
                    "evidence": "package.json:1",
                    "data": {"path": "package.json", "name": "package.json"},
                },
                {
                    "id": "ev-0002",
                    "kind": "absence",
                    "status": "confirmed",
                    "evidence": "검색(scope=., pattern=Dockerfile|Containerfile, result=없음)",
                    "data": {"scope": ".", "pattern": "Dockerfile|Containerfile", "result": "없음"},
                },
            ],
        }

        result = self.run_validator(legacy)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"valid": True, "errors": []})

    def test_snapshot_to_evidence_json_excludes_noise_and_records_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "package.json").write_text(
                '{"scripts":{"start":"node src/server.js"}}\n',
                encoding="utf-8",
            )
            src = repo / "src"
            src.mkdir()
            (src / "server.js").write_text(
                "const express = require('express')\n"
                "app.listen(process.env.PORT || 3000)\n",
                encoding="utf-8",
            )
            (repo / "node_modules").mkdir()
            (repo / "node_modules" / "ignored.js").write_text("ignored\n", encoding="utf-8")
            (repo / "vendor").mkdir()
            (repo / "vendor" / "ignored.py").write_text("ignored\n", encoding="utf-8")
            (repo / "logo.png").write_bytes(b"\x89PNG\x00binary")

            payload = self.run_collector(repo)

        files = {entry["path"] for entry in payload["snapshot"]["files"]}
        self.assertIn("package.json", files)
        self.assertIn("src/server.js", files)
        self.assertNotIn("node_modules/ignored.js", files)
        self.assertNotIn("vendor/ignored.py", files)
        self.assertNotIn("logo.png", files)

        evidence = payload["evidence"]
        self.assertTrue(
            any(item["kind"] == "manifest" and item["evidence"] == "package.json:1" for item in evidence)
        )
        self.assertTrue(
            any(item["kind"] == "runtime_entrypoint_hint" and item["evidence"] == "src/server.js:2" for item in evidence)
        )
        self.assertTrue(
            any(
                item["kind"] == "absence"
                and item["evidence"] == "검색(scope=., pattern=Dockerfile|Containerfile, result=없음)"
                for item in evidence
            )
        )

    def test_secret_values_are_redacted_before_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / ".env.example").write_text(
                "DATABASE_URL=postgres://localhost/app\n"
                "API_TOKEN=do-not-leak-this-token\n",
                encoding="utf-8",
            )

            payload = self.run_collector(repo)

        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertIn("API_TOKEN", rendered)
        self.assertIn("[REDACTED]", rendered)
        self.assertNotIn("do-not-leak-this-token", rendered)

    def test_subdirectory_must_stay_inside_repository_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()

            result = subprocess.run(
                ["python3", str(SCRIPT), str(repo), "--subdirectory", "../outside"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("analysis root must stay inside repository root", result.stderr)

    def test_language_and_platform_packs_collect_facts_without_component_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "pom.xml").write_text(
                "<project>\n<packaging>jar</packaging>\n<dependency>spring-boot</dependency>\n</project>\n",
                encoding="utf-8",
            )
            (repo / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
            (repo / "package.json").write_text(
                '{"packageManager":"pnpm@9","workspaces":["apps/*"],'
                '"scripts":{"start":"node src/server.js"}}\n',
                encoding="utf-8",
            )
            (repo / "yarn.lock").write_text("# lock\n", encoding="utf-8")
            (repo / "pyproject.toml").write_text("[project]\nname = 'lib'\n", encoding="utf-8")
            (repo / "go.mod").write_text("module example.com/service\ngo 1.22\n", encoding="utf-8")
            (repo / "web.csproj").write_text("<TargetFramework>net8.0</TargetFramework>\n", encoding="utf-8")
            (repo / "Gemfile").write_text("gem 'rails'\n", encoding="utf-8")
            (repo / "composer.json").write_text('{"require":{"laravel/framework":"*"}}\n', encoding="utf-8")
            (repo / "Cargo.toml").write_text("[package]\nname = 'worker'\n", encoding="utf-8")
            (repo / "Procfile").write_text("web: bundle exec puma\n", encoding="utf-8")
            (repo / "fly.toml").write_text("[http_service]\ninternal_port = 8080\n", encoding="utf-8")
            (repo / "render.yaml").write_text("services:\n  - type: web\n", encoding="utf-8")
            (repo / "railway.toml").write_text("[build]\nbuilder = 'NIXPACKS'\n", encoding="utf-8")
            (repo / "manifest.yml").write_text("applications:\n- name: cf-app\n", encoding="utf-8")
            (repo / "serverless.yml").write_text("functions:\n  api:\n", encoding="utf-8")
            (repo / "nx.json").write_text('{"extends":"nx/presets/npm.json"}\n', encoding="utf-8")
            (repo / "turbo.json").write_text('{"tasks":{"build":{}}}\n', encoding="utf-8")
            (repo / "Makefile").write_text("build:\n\tnpm run build\n", encoding="utf-8")
            (repo / "Taskfile.yml").write_text("tasks:\n  test:\n    cmds:\n      - pytest\n", encoding="utf-8")

            payload = self.run_collector(repo)

        evidence = payload["evidence"]
        languages = {item["data"].get("language") for item in evidence if item["kind"] == "language_manifest"}
        self.assertEqual(languages, {"java", "node", "python", "go", "dotnet", "ruby", "php", "rust"})
        managers = {item["data"].get("manager") for item in evidence if item["kind"] == "package_manager_hint"}
        self.assertTrue({"pnpm", "yarn"}.issubset(managers))
        platforms = {item["data"].get("platform") for item in evidence if item["kind"] == "platform_hint"}
        self.assertEqual(
            platforms,
            {"procfile", "fly", "render", "railway", "cloud_foundry", "serverless", "nx", "turbo", "make", "taskfile"},
        )
        self.assertFalse(any("deploy" in item["kind"] for item in evidence))

    def test_docker_compose_kubernetes_helm_and_kustomize_packs_collect_safe_typed_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            (repo / "Dockerfile").write_text(
                "FROM python:3.12\nWORKDIR /app\nCOPY . .\nRUN docker login -u user -p short-password-secret\nUSER app\nENV API_TOKEN=secret-value\n"
                "EXPOSE 8080\nENTRYPOINT [\"python\"]\nCMD [\"app.py\", \"--token\", \"docker-secret\"]\n"
                "HEALTHCHECK CMD curl -u user:password -H \"Authorization: Bearer docker-bearer\" -H \"Authorization: Basic basic-secret-value\" http://localhost:8080/health\n",
                encoding="utf-8",
            )
            (repo / "compose.yaml").write_text(
                "services:\n  api:\n    image: example/api\n    build: .\n    command: python app.py\n"
                "    entrypoint: [python]\n    ports: [\"8080:8080\"]\n    environment:\n      API_TOKEN: compose-secret\n      - LIST_TOKEN=list-secret\n"
                "    depends_on: [db]\n    profiles: [dev]\n    volumes: [data:/data]\n    networks: [backend]\n",
                encoding="utf-8",
            )
            manifests = repo / "k8s"
            manifests.mkdir()
            (manifests / "app.yaml").write_text(
                "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\nspec:\n  template:\n"
                "    spec:\n      containers:\n        - name: api\n          image: example/api:1\n"
                "          command: [python]\n          args: [app.py, --token, kube-secret, \"Authorization: Bearer kube-bearer\"]\n          ports:\n            - containerPort: 8080\n"
                "          env:\n            - name: API_TOKEN\n              value: should-not-leak\n          livenessProbe:\n            httpGet:\n              path: /health\n"
                "          volumeMounts:\n            - name: data\n              mountPath: /data\n      volumes:\n        - name: data\n---\napiVersion: v1\nkind: Service\nmetadata:\n  name: api\nspec:\n  ports:\n    - port: 80\n      targetPort: 8080\n",
                encoding="utf-8",
            )
            chart = repo / "chart"
            (chart / "templates").mkdir(parents=True)
            (chart / "Chart.yaml").write_text("name: api\nappVersion: 1.0\n", encoding="utf-8")
            (chart / "values.yaml").write_text("image:\n  repository: example/api\n", encoding="utf-8")
            (chart / "templates" / "deployment.yaml").write_text("kind: Deployment\n", encoding="utf-8")
            overlay = repo / "overlays" / "dev"
            overlay.mkdir(parents=True)
            (overlay / "kustomization.yaml").write_text(
                "resources:\n  - ../../k8s/app.yaml\npatches:\n  - patch.yaml\nimages:\n  - name: api\n"
                "configMapGenerator:\n  - name: config\nsecretGenerator:\n  - name: secret\nnamespace: dev\ncommonLabels:\n  team: platform\n",
                encoding="utf-8",
            )

            payload = self.run_collector(repo)

        evidence = payload["evidence"]
        kinds = {item["kind"] for item in evidence}
        self.assertTrue({"docker_instruction", "docker_env_key", "compose_service", "compose_service_field"}.issubset(kinds))
        instructions = {item["data"]["instruction"] for item in evidence if item["kind"] == "docker_instruction"}
        self.assertTrue({"FROM", "WORKDIR", "COPY", "RUN", "USER", "ENV", "EXPOSE", "ENTRYPOINT", "CMD", "HEALTHCHECK"}.issubset(instructions))
        compose_env_keys = {item["data"]["key"] for item in evidence if item["kind"] == "compose_env_key"}
        self.assertTrue({"API_TOKEN", "LIST_TOKEN"}.issubset(compose_env_keys))
        kubernetes_env_keys = {item["data"]["key"] for item in evidence if item["kind"] == "kubernetes_env_key"}
        self.assertIn("API_TOKEN", kubernetes_env_keys)
        self.assertTrue({"kubernetes_resource", "kubernetes_container_field", "kubernetes_env_key", "kubernetes_probe", "kubernetes_volume", "kubernetes_service_exposure"}.issubset(kinds))
        self.assertTrue({"helm_chart", "helm_values_key", "helm_template_resource", "kustomize_composition"}.issubset(kinds))
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("compose-secret", rendered)
        self.assertNotIn("list-secret", rendered)
        self.assertNotIn("should-not-leak", rendered)
        self.assertNotIn("docker-secret", rendered)
        self.assertNotIn("kube-secret", rendered)
        self.assertNotIn("user:password", rendered)
        self.assertNotIn("docker-bearer", rendered)
        self.assertNotIn("kube-bearer", rendered)
        self.assertNotIn("short-password-secret", rendered)
        self.assertNotIn("basic-secret-value", rendered)

    def test_nested_node_manager_conflicts_are_scoped_and_platform_facts_are_typed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            app = repo / "apps" / "api"
            app.mkdir(parents=True)
            (repo / "yarn.lock").write_text("# root lock\n", encoding="utf-8")
            (app / "package.json").write_text(
                '{"packageManager":"pnpm@9","scripts":{"start":"node server.js --token script-secret -H Authorization: Bearer script-bearer"}}\n',
                encoding="utf-8",
            )
            (app / "yarn.lock").write_text("# conflicting lock\n", encoding="utf-8")
            (repo / "Procfile").write_text("web: node server.js --token procfile-secret -H Authorization: Bearer procfile-bearer\n", encoding="utf-8")
            (repo / "fly.toml").write_text("[http_service]\ninternal_port = 8080\n", encoding="utf-8")
            (repo / "settings.yaml").write_text("DATABASE_URL: postgres://user:password@db/app\n", encoding="utf-8")
            (repo / "appsettings.json").write_text('{"ConnectionStrings":{"Default":"ignored"},"Logging":{"LogLevel":"Information"}}\n', encoding="utf-8")
            (repo / "nx.json").write_text('{"extends":"nx/presets/npm.json","targetDefaults":{}}\n', encoding="utf-8")
            (repo / "turbo.json").write_text('{"tasks":{"build":{}}}\n', encoding="utf-8")

            payload = self.run_collector(repo)

        evidence = payload["evidence"]
        conflicts = [item for item in evidence if item["kind"] == "package_manager_conflict"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["data"]["scope"], "apps/api")
        process = next(item for item in evidence if item["kind"] == "platform_process")
        self.assertEqual(process["data"]["process_type"], "web")
        platform_fields = {item["data"].get("field") for item in evidence if item["kind"] == "platform_config_hint"}
        self.assertIn("internal_port", platform_fields)
        self.assertTrue({"extends", "tasks"}.issubset(platform_fields))
        config_keys = {item["data"].get("key") for item in evidence if item["kind"] == "config_key"}
        self.assertIn("DATABASE_URL", config_keys)
        self.assertTrue({"ConnectionStrings", "ConnectionStrings.Default"}.issubset(config_keys))
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("script-secret", rendered)
        self.assertNotIn("procfile-secret", rendered)
        self.assertNotIn("script-bearer", rendered)
        self.assertNotIn("procfile-bearer", rendered)
        self.assertNotIn("user:password", rendered)


if __name__ == "__main__":
    unittest.main()

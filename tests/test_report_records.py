import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import report_contract
import report_records


def valid_document_payload():
    return {
        "mode": "summary",
        "subjects": [
            {
                "subject_id": "deployable:jpetstore",
                "kind": "deployable",
                "display_name": "JPetStore",
            },
            {
                "subject_id": "dependency:mysql",
                "kind": "dependency",
                "display_name": "MySQL",
            },
        ],
        "claims": [
            {
                "claim_id": "claim:runtime",
                "section_key": "component_cards",
                "subject_id": "deployable:jpetstore",
                "field": "execution_form",
                "value": "Spring Boot application",
                "status": "confirmed",
                "evidence": ["pom.xml:1"],
                "reason": "",
            }
        ],
        "relationships": [
            {
                "edge_id": "edge:jpetstore:mysql",
                "source_subject_id": "deployable:jpetstore",
                "target_subject_id": "dependency:mysql",
                "attributes": {
                    "kind": "database",
                    "mechanism": "JDBC",
                },
                "status": "confirmed",
                "evidence": ["src/main/resources/application.yml:8"],
                "reason": "",
            }
        ],
    }


class ReportRecordTests(unittest.TestCase):
    def test_document_rejects_inferred_claim_without_reason(self):
        payload = valid_document_payload()
        payload["claims"][0]["status"] = "inferred"

        with self.assertRaisesRegex(ValueError, "reason"):
            report_records.parse_report_document(payload)

    def test_unknown_claim_accepts_empty_reason_from_tool_contract(self):
        payload = valid_document_payload()
        payload["claims"][0]["status"] = "unknown"
        payload["claims"][0]["value"] = "확인되지 않음"

        document = report_records.parse_report_document(payload)

        self.assertEqual(document.claims[0].reason, "")

    def test_document_rejects_duplicate_claim_id(self):
        payload = valid_document_payload()
        payload["claims"].append(copy.deepcopy(payload["claims"][0]))

        with self.assertRaisesRegex(ValueError, "claim_id"):
            report_records.parse_report_document(payload)

    def test_document_rejects_duplicate_edge_id(self):
        payload = valid_document_payload()
        payload["relationships"].append(copy.deepcopy(payload["relationships"][0]))

        with self.assertRaisesRegex(ValueError, "edge_id"):
            report_records.parse_report_document(payload)

    def test_document_rejects_dangling_relationship_subject(self):
        payload = valid_document_payload()
        payload["relationships"][0]["target_subject_id"] = "dependency:missing"

        with self.assertRaisesRegex(ValueError, "dependency:missing"):
            report_records.parse_report_document(payload)

    def test_document_rejects_invalid_status(self):
        payload = valid_document_payload()
        payload["claims"][0]["status"] = "probably"

        with self.assertRaisesRegex(ValueError, "status"):
            report_records.parse_report_document(payload)

    def test_document_rejects_markdown_in_value(self):
        payload = valid_document_payload()
        payload["claims"][0]["value"] = "[JPetStore](https://invalid.example)"

        with self.assertRaisesRegex(ValueError, "Markdown"):
            report_records.parse_report_document(payload)

    def test_document_rejects_absolute_evidence_path(self):
        payload = valid_document_payload()
        payload["claims"][0]["evidence"] = ["/workspace/pom.xml:1"]

        with self.assertRaisesRegex(ValueError, "repository-relative"):
            report_records.parse_report_document(payload)

    def test_document_rejects_secret_like_value(self):
        payload = valid_document_payload()
        payload["claims"][0]["value"] = "password=hunter2"

        with self.assertRaisesRegex(ValueError, "secret"):
            report_records.parse_report_document(payload)

    def test_contract_validation_reports_unknown_claim_field(self):
        payload = valid_document_payload()
        payload["claims"][0]["field"] = "model_generated_markdown"
        document = report_records.parse_report_document(payload)

        diagnostics = report_records.validate_document(
            document, report_contract.load_report_contract()
        )

        self.assertEqual([diagnostic.code for diagnostic in diagnostics], ["UNKNOWN_FIELD"])

    def test_valid_payload_is_loaded_into_frozen_records(self):
        document = report_records.parse_report_document(valid_document_payload())

        self.assertEqual(document.mode, "summary")
        self.assertEqual(document.claims[0].evidence, ("pom.xml:1",))
        self.assertEqual(
            document.relationships[0].attributes,
            (("kind", "database"), ("mechanism", "JDBC")),
        )
        with self.assertRaises(Exception):
            document.mode = "detailed"

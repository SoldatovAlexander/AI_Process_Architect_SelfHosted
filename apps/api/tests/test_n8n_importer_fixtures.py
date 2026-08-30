import json
from pathlib import Path
from xml.etree import ElementTree as ET

from jsonschema import Draft202012Validator


FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "n8n_importer" / "v1"
REQUIRED_FIXTURE_FILES = {
    "mapping.expected.json",
    "process.expected.bpmn",
    "quality_report.expected.json",
    "quality_report.expected.md",
    "semantic_graph.expected.json",
    "source_ref.json",
    "technical_graph.expected.json",
}
BPMN_DEFINITIONS_TAG = "{http://www.omg.org/spec/BPMN/20100524/MODEL}definitions"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_n8n_importer_fixture_pack_is_complete_and_valid():
    index = _load_json(FIXTURE_ROOT / "fixture_index.json")
    schema = _load_json(FIXTURE_ROOT / "process_template_schema_v1.json")
    validator = Draft202012Validator(schema)
    fixture_dirs = {path.name: path for path in (FIXTURE_ROOT / "fixtures").iterdir() if path.is_dir()}

    assert len(index["fixtures"]) == 5
    assert set(fixture_dirs) == {item["id"].replace(".", "__") for item in index["fixtures"]}

    for item in index["fixtures"]:
        fixture_dir = fixture_dirs[item["id"].replace(".", "__")]
        assert REQUIRED_FIXTURE_FILES <= {path.name for path in fixture_dir.iterdir()}

        source_ref = _load_json(fixture_dir / "source_ref.json")
        assert source_ref["template_id"] == item["template_id"]
        assert source_ref["archive_blob_sha"] == item["source_blob_sha"]
        assert source_ref["license_status"] == "review_required"
        assert source_ref["source_payload_in_bundle"] is False

        semantic_graph = _load_json(fixture_dir / "semantic_graph.expected.json")
        validator.validate(semantic_graph)

        bpmn_root = ET.parse(fixture_dir / "process.expected.bpmn").getroot()
        assert bpmn_root.tag == BPMN_DEFINITIONS_TAG


def test_all_fixture_pack_json_documents_parse():
    for path in FIXTURE_ROOT.rglob("*.json"):
        _load_json(path)

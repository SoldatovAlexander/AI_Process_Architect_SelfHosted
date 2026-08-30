import json
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
LIBRARY_ROOT = REPOSITORY_ROOT / "data" / "process_library" / "n8n" / "v1"
IMPORTER_FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "n8n_importer" / "v1"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_n8n_process_library_catalog_is_internally_consistent():
    library = _load_json(LIBRARY_ROOT / "n8n_process_library_50_v1.json")
    processes = library["processes"]

    assert library["schema_version"] == "1.0"
    assert library["library_version"] == "0.1.0"
    assert library["counts"]["total"] == len(processes) == 50
    assert {item["rank"] for item in processes} == set(range(1, 51))
    assert len({item["id"] for item in processes}) == 50
    assert len({item["source"]["template_id"] for item in processes}) == 50

    assert Counter(item["category"] for item in processes) == library["counts"]["by_category"]
    assert Counter(item["priority"] for item in processes) == library["counts"]["by_priority"]
    assert sum(item["ai_required"] for item in processes) == library["counts"]["with_ai"]
    assert sum(item["human_in_loop"] for item in processes) == library["counts"]["with_hitl"]

    for item in processes:
        source = item["source"]
        assert source["provider"] == "n8n"
        assert source["license_status"] == "review_required"
        assert source["url"].startswith(f"https://n8n.io/workflows/{source['template_id']}-")
        assert item["source_json_status"] == "pending_fetch"
        assert item["semantic_model_status"] == "draft"


def test_n8n_process_library_shared_contracts_match_importer_fixtures():
    shared_files = ("CODEX_PROCESS_LIBRARY_GUIDE_v1.md", "process_template_schema_v1.json")
    for filename in shared_files:
        assert (LIBRARY_ROOT / filename).read_bytes() == (IMPORTER_FIXTURE_ROOT / filename).read_bytes()

    Draft202012Validator.check_schema(_load_json(LIBRARY_ROOT / "process_template_schema_v1.json"))


def test_n8n_process_library_markdown_lists_every_catalog_entry():
    catalog = _load_json(LIBRARY_ROOT / "n8n_process_library_50_v1.json")
    markdown = (LIBRARY_ROOT / "n8n_process_library_50_v1.md").read_text(encoding="utf-8")
    for item in catalog["processes"]:
        assert f"`{item['id']}`" in markdown


def test_process_library_batch_071_300_is_valid_and_collision_reviewed():
    root = REPOSITORY_ROOT / "data" / "process_library" / "batch_071_300" / "v1"
    batch = _load_json(root / "process_library_230_batch_v1.json")
    validation = _load_json(root / "VALIDATION_REPORT_v1.json")
    collision_report = _load_json(root / "COLLISION_REPORT_v1.json")
    agent_schema = _load_json(root / "agent_export_extension_schema_v1.json")
    localizations = _load_json(root / "LOCALIZATIONS_v1.json")
    processes = batch["processes"]

    assert len(processes) == batch["count"] == validation["count"] == 230
    assert {item["library_number"] for item in processes} == set(range(71, 301))
    assert len({item["id"] for item in processes}) == 230
    assert set(localizations["titles"]) == {item["id"] for item in processes}
    assert all(value["ru"] and value["es"] for value in localizations["titles"].values())
    assert sum(item["agent_export"]["enabled"] for item in processes) == 28
    assert collision_report["summary"] == {
        "incoming": 230,
        "exact_duplicates_skipped": 4,
        "possible_variants_kept": 4,
        "product_templates_added": 226,
    }
    Draft202012Validator.check_schema(agent_schema)
    agent_validator = Draft202012Validator(agent_schema)
    for item in processes:
        assert item["provenance"]["license_status"] == "review_required"
        assert item["provenance"]["verbatim_workflow_included"] is False
        agent_validator.validate(item["agent_export"])

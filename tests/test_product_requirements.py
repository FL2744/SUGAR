import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "product" / "requirements" / "state_product.v1.json"


def _load_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_state_product_contract_has_unique_well_formed_requirements():
    contract = _load_contract()
    requirements = contract["requirements"]
    assert requirements

    ids = [item["id"] for item in requirements]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"STATE-P[012]-\d{3}", value) for value in ids)

    for item in requirements:
        assert item["priority"] in {"P0", "P1", "P2"}
        assert item["status"] in {"not_met", "partially_met", "met", "deferred"}
        assert item["category"].strip()
        assert item["title"].strip()
        assert item["requirement"].strip()
        assert item["verification"].strip()
        assert item["acceptance"] and all(value.strip() for value in item["acceptance"])


def test_every_p0_requirement_has_multiple_acceptance_checks():
    contract = _load_contract()
    p0 = [item for item in contract["requirements"] if item["priority"] == "P0"]
    assert p0
    for item in p0:
        assert len(item["acceptance"]) >= 2, item["id"]


def test_product_contract_is_linked_from_documentation_index():
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "product/state-product-contract.md" in index
    assert "state_product.v1.json" in index


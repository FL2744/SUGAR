from sugar_core.collection_coverage import SourceCoverage, classify_collection_error, coverage_payload


class PartialError(RuntimeError):
    partial_records = [object()]


def test_error_classification_distinguishes_access_partial_and_failure():
    assert classify_collection_error(RuntimeError("HTTP 403 forbidden")) == "unavailable"
    assert classify_collection_error(ValueError("X requires credential(s): x_bearer_token")) == "unavailable"
    assert classify_collection_error(PartialError("connection dropped")) == "partial"
    assert classify_collection_error(RuntimeError("unexpected parser failure")) == "failed"


def test_coverage_payload_separates_zero_result_from_failure():
    payload = coverage_payload([
        SourceCoverage(source="a", status="zero_result", records=0),
        SourceCoverage(source="b", status="failed", records=0, reason="network failure"),
    ], terms=["example"])
    assert payload["overall_status"] == "partial"
    assert payload["sources"]["a"]["status"] == "zero_result"
    assert payload["sources"]["b"]["status"] == "failed"

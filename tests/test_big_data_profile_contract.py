from pathlib import Path


def test_unclassified_profile_benchmark_is_an_expected_empty_state():
    source = (Path(__file__).resolve().parents[1] / "routers" / "big_data.py").read_text(encoding="utf-8")

    assert "classification_response = db.table(\"local_commercial_classifications\")" in source
    assert 'getattr(classification_response, "data", None) or {}' in source
    assert 'return {"status": "insufficient_data", "reason": "El local no tiene categoría homologada."}' in source
    assert 'select("local_id,sales_net")' in source

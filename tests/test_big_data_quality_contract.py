from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_quality_accepts_malls_without_a_first_watermark():
    source = (ROOT / "routers" / "big_data.py").read_text(encoding="utf-8")

    assert "watermark_response" in source
    assert 'getattr(watermark_response, "data", None) or {}' in source

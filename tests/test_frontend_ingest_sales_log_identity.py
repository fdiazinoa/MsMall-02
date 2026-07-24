from pathlib import Path


def test_ingest_sales_accepts_hour_only_values_and_resolves_local_before_time_validation():
    repo = Path(__file__).resolve().parents[1]
    source = (repo / "api.ts").read_text(encoding="utf-8")

    assert "let hourOnly = text.match(/^(\\d{1,2})$/);" in source
    assert "return `${pad2(hh)}:00:00`;" in source

    store_lookup = source.index("const store = storeMap.get(normalizedStoreCode);")
    time_validation = source.index("error: `Formato de hora inválido: ${horaRaw}`")
    assert store_lookup < time_validation

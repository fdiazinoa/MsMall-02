from pathlib import Path


def test_saving_corrected_import_config_reactivates_only_suspended_local():
    repo = Path(__file__).resolve().parents[1]
    source = (repo / "api.ts").read_text(encoding="utf-8")
    start = source.index("async saveImportConfig")
    end = source.index("async deleteImportConfig", start)
    segment = source[start:end]

    assert ".select('id, codigo_interno, processing_status')" in segment
    assert "existingProcessingStatus === 'SUSPENDED_AUTH_ERROR'" in segment
    assert "dbPayload.processing_status = 'IDLE'" in segment
    assert "dbPayload.consecutive_failures = 0" in segment

from pathlib import Path


def test_railway_worker_entrypoint_is_service_friendly():
    repo = Path(__file__).resolve().parents[1]
    script = (repo / "start_worker.sh").read_text(encoding="utf-8")
    dockerfile = (repo / "Dockerfile.worker").read_text(encoding="utf-8")
    readme = (repo / "README.md").read_text(encoding="utf-8")

    assert 'WORKER_POLL_SECONDS="${WORKER_POLL_SECONDS:-300}"' in script
    assert "python3 -u worker_importacion.py" in script
    assert ">> worker.log" not in script
    assert "trap " in script

    assert 'CMD ["./start_worker.sh"]' in dockerfile
    assert "ENABLE_API_SCHEDULER=false" in dockerfile

    assert "ftp-import-worker" in readme
    assert "Start Command como `./start_worker.sh`" in readme

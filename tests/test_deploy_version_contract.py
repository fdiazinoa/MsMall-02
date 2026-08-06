import json
from pathlib import Path


def test_deploy_version_is_centralized_and_visible():
    repo = Path(__file__).resolve().parents[1]
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    app_source = (repo / "App.tsx").read_text(encoding="utf-8")
    version_source = (repo / "appVersion.ts").read_text(encoding="utf-8")
    vite_source = (repo / "vite.config.ts").read_text(encoding="utf-8")

    assert version == "20"
    assert version.isdigit()
    assert "MSMALL_FOOTER_TEXT" in app_source
    assert "© MercaSend, SRL. MsMall v.${MSMALL_DEPLOY_VERSION}" in version_source
    assert "__MSMALL_DEPLOY_VERSION__" in vite_source
    assert "MsMall v.20" not in app_source


def test_deploy_version_commands_are_available():
    repo = Path(__file__).resolve().parents[1]
    package_json = json.loads((repo / "package.json").read_text(encoding="utf-8"))
    scripts = package_json["scripts"]

    assert scripts["deploy:version:show"] == "node scripts/deploy-version.mjs show"
    assert scripts["deploy:version:bump"] == "node scripts/deploy-version.mjs bump"
    assert scripts["deploy:version:set"] == "node scripts/deploy-version.mjs set"

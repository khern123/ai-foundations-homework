import pytest

import audit


@pytest.fixture(autouse=True)
def isolated_audit_file(monkeypatch, tmp_path):
    """Every test writes audit entries to its own throwaway file, never output/audit_trail.json."""
    path = tmp_path / "audit_trail.json"
    monkeypatch.setattr(audit, "AUDIT_PATH", path)
    return path

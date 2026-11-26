"""Synthetic transport failures; actual historical original remains SHA-pinned."""
import hashlib
import io
import json
import zipfile

import pytest

from scripts import mvp016_source_recovery as recovery


def sample(*, members=None, **updates):
    index = {"schema": "BET_MVP_002_FIXED_COHORT_INDEX_V1", "bet_authority": False,
             "pit_certified": False, "original_cohort": [], "processed": [],
             "not_processed": [], "source_report_sha256": "a" * 64, **updates}
    original = json.dumps(index).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in (members or [("cohort-index.json", original)]):
            archive.writestr(name, value)
    raw = stream.getvalue()
    contract = {"zip_size": len(raw), "zip_sha256": hashlib.sha256(raw).hexdigest(),
                "member": "cohort-index.json", "member_sha256": hashlib.sha256(original).hexdigest(),
                "upstream_hashes": {"source_report_sha256": "a" * 64}}
    return raw, contract


def test_exact_original_bytes_and_references_preserved():
    raw, contract = sample()
    assert json.loads(recovery.verify_original(raw, contract))["processed"] == []


@pytest.mark.parametrize("mutation", ["zip_sha256", "member_sha256", "zip_size", "upstream_hashes"])
def test_wrong_hash_size_or_referenced_hash_rejected(mutation):
    raw, contract = sample()
    contract[mutation] = {"source_report_sha256": "b" * 64} if mutation == "upstream_hashes" else (
        0 if mutation == "zip_size" else "0" * 64)
    with pytest.raises(ValueError, match="MVP016_ORIGINAL"):
        recovery.verify_original(raw, contract)


@pytest.mark.parametrize("updates", [{"bet_authority": True}, {"pit_certified": True},
                                      {"processed": ["phantom"]}, {"original_cohort": ["late"]},
                                      {"schema": "UNKNOWN"}])
def test_fabricated_cohort_or_authority_remains_blocked(updates):
    raw, contract = sample(**updates)
    with pytest.raises(ValueError, match="INDEX_CONTRACT"):
        recovery.verify_original(raw, contract)


@pytest.mark.parametrize("name", ["../cohort-index.json", "/cohort-index.json", "extra.json"])
def test_unexpected_or_unsafe_archive_member_rejected(name):
    raw, contract = sample(members=[(name, b"{}")])
    with pytest.raises(ValueError, match="MEMBERS_OR_CRC"):
        recovery.verify_original(raw, contract)


def test_missing_read_credential_does_not_fallback_or_write(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_ARCHIVE_READ_TOKEN", raising=False)
    monkeypatch.setattr(recovery, "api_read", lambda *a, **k: pytest.fail("unexpected request"))
    with pytest.raises(ValueError, match="CREDENTIAL_MISSING"):
        recovery.recover(tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_public_archive_rejected_before_original_download(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("RESEARCH_ARCHIVE_READ_TOKEN", "synthetic-test-token")
    def read(path, token, **kwargs):
        calls.append(path)
        return json.dumps({"private": False}).encode()
    monkeypatch.setattr(recovery, "api_read", read)
    with pytest.raises(ValueError, match="MUST_REMAIN_PRIVATE"):
        recovery.recover(tmp_path / "out")
    assert len(calls) == 1 and not (tmp_path / "out").exists()


def test_existing_output_not_overwritten(tmp_path, monkeypatch):
    raw, contract = sample()
    contract.update(source_run=1, source_artifact=2, commit="c" * 40, schema="synthetic")
    config = tmp_path / "contract.json"
    config.write_text(json.dumps(contract))
    monkeypatch.setattr(recovery, "CONTRACT", config)
    source = tmp_path / "source.zip"
    source.write_bytes(raw)
    target = tmp_path / "restored"
    result = recovery.recover(target, local_zip=source)
    assert result["all_upstream_bytes_verified"] is False
    before = (target / "cohort-index.json").read_bytes()
    with pytest.raises(FileExistsError):
        recovery.recover(target, local_zip=source)
    assert (target / "cohort-index.json").read_bytes() == before


def test_original_contract_keeps_existing_pins():
    contract = json.loads(recovery.CONTRACT.read_bytes())
    assert contract["member_sha256"] == "ebeb64f1fc27328c0ff5f063ede33ec1d08615e482d4a017680ea0d5813b9aa0"
    assert contract["zip_sha256"] == "2b2683ba14774b637237f99484f1b8256321744c0552c0d30a5635bd549a6cfa"
    assert len(contract["commit"]) == 40

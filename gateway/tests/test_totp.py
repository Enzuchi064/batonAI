import pytest

from baton import totp
from baton.audit import AuditLog
from baton.pairing import PairingManager
from baton.virtual_device import VirtualDevice, VirtualPairingError

# RFC 6238, apéndice B: secreto ASCII "12345678901234567890" en base32.
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
RFC_VECTORS = [
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
    (20000000000, "353130"),
]


def test_rfc6238_vectors():
    for at, expected in RFC_VECTORS:
        assert totp.totp(RFC_SECRET, at=at) == expected


def test_verify_accepts_current_and_neighbours():
    at = 1_700_000_000
    code = totp.totp(RFC_SECRET, at=at)
    assert totp.verify(RFC_SECRET, code, at=at) == at // 30
    assert totp.verify(RFC_SECRET, code, at=at + 30) == at // 30
    assert totp.verify(RFC_SECRET, code, at=at - 30) == at // 30
    assert totp.verify(RFC_SECRET, code, at=at + 90) is None


def test_verify_rejects_bad_input():
    assert totp.verify(RFC_SECRET, "000000", at=59) is None
    assert totp.verify(RFC_SECRET, "12345", at=59) is None
    assert totp.verify(RFC_SECRET, "abcdef", at=59) is None


def test_otpauth_uri_has_expected_fields():
    uri = totp.otpauth_uri(RFC_SECRET, "baton-3f2a9c")
    assert uri.startswith("otpauth://totp/batonAI%3Abaton-3f2a9c?")
    assert f"secret={RFC_SECRET}" in uri
    assert "issuer=batonAI" in uri
    assert "digits=6" in uri
    assert "period=30" in uri


@pytest.fixture
def device(tmp_path):
    audit = AuditLog(tmp_path / "baton.db")
    pairing = PairingManager(audit)
    item = VirtualDevice.create(
        audit, pairing, tmp_path / "virtual_device.json"
    )
    yield item
    audit.close()


def test_virtual_device_pairs_with_confirm(device):
    code = totp.totp(device.secret)
    result = device.pair(code, "DESKTOP-TEST")
    assert result["status"] == "needs_confirm"
    assert len(result["sas"]) == 4

    confirmed = device.confirm(result["pair_id"])
    assert confirmed["status"] == "paired"
    assert device.paired_to == "DESKTOP-TEST"
    assert device.info()["paired"] is True


def _bad_code(device: VirtualDevice) -> str:
    good = totp.totp(device.secret)
    return "000000" if good != "000000" else "000001"


def test_virtual_device_rejects_bad_code(device):
    with pytest.raises(VirtualPairingError) as exc:
        device.pair(_bad_code(device), "DESKTOP-TEST")
    assert exc.value.code == "bad_code"


def test_virtual_device_rate_limits(device):
    for _ in range(5):
        with pytest.raises(VirtualPairingError):
            device.pair(_bad_code(device), "DESKTOP-TEST")
    with pytest.raises(VirtualPairingError) as exc:
        device.pair(_bad_code(device), "DESKTOP-TEST")
    assert exc.value.code == "rate_limited"


def test_virtual_device_unpair_keeps_secret(device):
    code = totp.totp(device.secret)
    pending = device.pair(code, "DESKTOP-TEST")
    device.confirm(pending["pair_id"])
    secret = device.secret

    device.unpair()
    assert device.paired_to is None
    assert device.secret == secret


def test_virtual_device_reset_changes_identity(device):
    old_id, old_secret = device.device_id, device.secret
    device.reset()
    assert device.device_id != old_id
    assert device.secret != old_secret

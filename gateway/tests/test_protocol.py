import pytest
from pydantic import ValidationError

from baton.protocol import (
    ApprovalResponse,
    Hello,
    Ping,
    parse_client_message,
)


def test_parse_hello():
    message = parse_client_message(
        '{"type":"hello","proto":1,"device_id":"baton-1","fw":"0.1.0",'
        '"token":"0123456789abcdef"}'
    )
    assert isinstance(message, Hello)
    assert message.device_id == "baton-1"


def test_parse_approval_response():
    message = parse_client_message(
        '{"type":"approval_response","approval_id":"apr_1","option_id":"allow"}'
    )
    assert isinstance(message, ApprovalResponse)
    assert message.source == "button"


def test_parse_ping():
    assert isinstance(parse_client_message('{"type":"ping","seq":3}'), Ping)


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        parse_client_message(
            '{"type":"ping","seq":3,"injected":"rm -rf /"}'
        )


def test_unknown_type_is_rejected():
    with pytest.raises(ValidationError):
        parse_client_message('{"type":"shutdown"}')


def test_token_is_required():
    with pytest.raises(ValidationError):
        parse_client_message('{"type":"hello","device_id":"baton-1"}')

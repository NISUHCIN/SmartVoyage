import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt as pyjwt

from backend.auth import create_token, verify_token
from core.config import Config


def test_create_and_verify_token_roundtrip():
    token = create_token(42, "tester")
    payload = verify_token(token)
    assert payload["user_id"] == 42
    assert payload["username"] == "tester"
    assert "exp" in payload and "iat" in payload


def test_verify_token_rejects_tampered_token():
    token = create_token(1, "alice")
    assert verify_token(token + "x") is None


def test_verify_token_rejects_garbage():
    assert verify_token("not-a-jwt") is None


def test_verify_token_rejects_expired_token():
    conf = Config()
    expired = pyjwt.encode({"user_id": 1, "exp": 0}, conf.jwt_secret, algorithm="HS256")
    assert verify_token(expired) is None

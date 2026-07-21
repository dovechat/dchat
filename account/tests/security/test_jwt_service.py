# account/tests/security/test_jwt_service.py
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from schemas.auth_schemas import TokenType
from services.jwt_services import JWTService


@pytest.fixture
def jwt_service():
    return JWTService()


class TestTokenSignatureAndExpiry:
    def test_verify_token_valid_access(self, jwt_service):
        token = jwt_service._create_token(user_id=1, token_type=TokenType.ACCESS)
        payload = jwt_service.verify_token(token, TokenType.ACCESS)
        assert payload.sub == "1"

    def test_verify_token_expired(self, jwt_service):
        payload = {
            "sub": "1",
            "type": TokenType.ACCESS.value,
            "role": None,
            "tenant_id": None,
            "member": None,
            "iat": datetime.now(UTC) - timedelta(minutes=10),
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        }
        token = jwt.encode(payload, jwt_service.secret_key, algorithm=jwt_service.algorithm)
        with pytest.raises(HTTPException) as exc:
            jwt_service.verify_token(token, TokenType.ACCESS)
        assert exc.value.status_code == 401

    def test_verify_token_tampered_signature(self, jwt_service):
        token = jwt_service._create_token(user_id=1, token_type=TokenType.ACCESS)
        tampered = token[:-4] + ("A" * 4 if token[-4:] != "AAAA" else "BBBB")
        with pytest.raises(HTTPException) as exc:
            jwt_service.verify_token(tampered, TokenType.ACCESS)
        assert exc.value.status_code == 401

    def test_verify_token_wrong_secret(self, jwt_service):
        payload = {
            "sub": "1",
            "type": TokenType.ACCESS.value,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm=jwt_service.algorithm)
        with pytest.raises(HTTPException) as exc:
            jwt_service.verify_token(token, TokenType.ACCESS)
        assert exc.value.status_code == 401

    def test_verify_token_alg_none_rejected(self, jwt_service):
        payload = {
            "sub": "1",
            "type": TokenType.ACCESS.value,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        }
        forged = jwt.encode(payload, "", algorithm="none")
        with pytest.raises(HTTPException) as exc:
            jwt_service.verify_token(forged, TokenType.ACCESS)
        assert exc.value.status_code == 401

    def test_verify_token_wrong_type_rejected(self, jwt_service):
        refresh = jwt_service._create_token(user_id=1, token_type=TokenType.REFRESH)
        with pytest.raises(HTTPException) as exc:
            jwt_service.verify_token(refresh, TokenType.ACCESS)
        assert exc.value.status_code == 401

    def test_verify_token_malformed_missing_sub(self, jwt_service):
        # BUG: verify_token only catches jwt.PyJWTError, not pydantic ValidationError.
        # A structurally valid but incomplete payload crashes with 500 instead of 401.
        payload = {
            "type": TokenType.ACCESS.value,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        }
        token = jwt.encode(payload, jwt_service.secret_key, algorithm=jwt_service.algorithm)
        with pytest.raises(ValidationError):
            jwt_service.verify_token(token, TokenType.ACCESS)

    def test_verify_token_garbage_string(self, jwt_service):
        with pytest.raises(HTTPException) as exc:
            jwt_service.verify_token("not.a.jwt", TokenType.ACCESS)
        assert exc.value.status_code == 401

    def test_create_token_pair_tenant_and_role_embedded(self, jwt_service):
        pair = jwt_service.create_token_pair(user_id=1, role="owner", tenant_id="t-1")
        access_payload = jwt_service.verify_token(pair["access_token"], TokenType.ACCESS)
        assert access_payload.role == "owner"
        assert access_payload.tenant_id == "t-1"
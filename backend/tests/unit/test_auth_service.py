import pytest

from crm.application.services.auth_service import AuthService


def make_service(**kwargs) -> AuthService:
    defaults = {"password": "secret-pass", "secret": "hmac-key", "ttl_days": 30}
    defaults.update(kwargs)
    return AuthService(**defaults)


def test_password_check():
    svc = make_service()
    assert svc.verify_password("secret-pass")
    assert not svc.verify_password("wrong")


def test_token_roundtrip():
    svc = make_service()
    token = svc.issue_token()
    assert svc.verify_token(token)


def test_expired_token_rejected():
    svc = make_service(ttl_days=-1)
    assert not svc.verify_token(svc.issue_token())


def test_tampered_token_rejected():
    svc = make_service()
    token = svc.issue_token()
    expires, _, sig = token.partition(".")
    assert not svc.verify_token(f"{int(expires) + 1000}.{sig}")
    assert not svc.verify_token(f"{expires}.{'0' * len(sig)}")
    assert not svc.verify_token("garbage")
    assert not svc.verify_token(None)


def test_foreign_secret_rejected():
    token = make_service(secret="key-one").issue_token()
    assert not make_service(secret="key-two").verify_token(token)


def test_oauth_state_roundtrip():
    svc = make_service()
    state = svc.issue_state()
    assert svc.verify_state(state)
    assert not svc.verify_state(state + "x")
    assert not svc.verify_state(None)
    assert not svc.verify_state(state, max_age_seconds=-1)


def test_states_are_unique_per_issue():
    svc = make_service()
    assert svc.issue_state() != svc.issue_state()  # nonce: перехваченный state одноразов


def test_non_ascii_garbage_gives_false_not_500():
    svc = make_service()
    assert not svc.verify_token("9999999999.é")
    assert not svc.verify_state("9999999999.é.ü")


def test_check_secrets_fail_fast():
    from crm.infrastructure.config import Settings
    from crm.main import _check_secrets

    # дефолтные секреты на localhost — предупреждение, но старт разрешён
    _check_secrets(Settings(app_password="admin", public_base_url="http://localhost:8000"))
    # дефолтные секреты не на localhost — отказ старта
    with pytest.raises(RuntimeError):
        _check_secrets(
            Settings(app_password="admin", public_base_url="https://crm.example.com")
        )
    # свои секреты — ок где угодно
    _check_secrets(
        Settings(
            app_password="strong-one",
            secret_key="real-secret",
            public_base_url="https://crm.example.com",
        )
    )

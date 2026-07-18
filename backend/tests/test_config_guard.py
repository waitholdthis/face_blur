"""Production settings guard: insecure defaults must block go-live."""
from app.config import Settings, validate_production_settings


def _settings(**overrides) -> Settings:
    base = dict(
        environment="production",
        jwt_secret="change-me-in-production-please-32chars-min",
        admin_password="admin123",
        cors_origins="*",
    )
    base.update(overrides)
    return Settings(**base)


def test_development_mode_is_not_guarded():
    assert validate_production_settings(_settings(environment="development")) == []


def test_production_rejects_all_insecure_defaults():
    problems = validate_production_settings(_settings())
    assert len(problems) == 3
    joined = " ".join(problems)
    assert "JWT_SECRET" in joined
    assert "ADMIN_PASSWORD" in joined
    assert "CORS_ORIGINS" in joined


def test_production_rejects_short_secret_even_if_changed():
    problems = validate_production_settings(
        _settings(jwt_secret="short-secret", admin_password="a-strong-password!", cors_origins="https://app.example.com")
    )
    assert problems == ["JWT_SECRET must be a unique random value of at least 32 characters"]


def test_production_accepts_hardened_settings():
    problems = validate_production_settings(
        _settings(
            jwt_secret="f" * 64,
            admin_password="a-strong-unique-password",
            cors_origins="https://app.example.com,https://www.example.com",
        )
    )
    assert problems == []

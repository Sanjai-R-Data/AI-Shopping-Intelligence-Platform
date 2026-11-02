"""
AI-Powered Multilingual Shopping Intelligence Platform
Configuration Management Unit Tests.
"""

from pydantic import SecretStr
from backend.app.core.config import Settings, get_settings


def test_settings_initialization():
    """Verify default settings load cleanly with expected metadata."""
    settings = get_settings()
    assert "AI-Powered Multilingual Shopping Intelligence Platform" in settings.APP_NAME
    assert settings.APP_VERSION == "0.1.0"
    assert settings.DATABASE_URL.startswith("sqlite:///")
    assert settings.is_development is True


def test_secret_str_masking():
    """
    Verify that sensitive configuration values (API keys, secrets) are wrapped in SecretStr
    and are never exposed via standard repr() or str().
    """
    settings = Settings(
        GEMINI_API_KEY=SecretStr("super-secret-gemini-key"),
        PAYPAL_CLIENT_SECRET=SecretStr("super-secret-paypal-secret"),
        CHANNEL3_API_KEY=SecretStr("super-secret-channel3-key"),
    )

    # String and repr representations must mask secrets
    assert "super-secret-gemini-key" not in str(settings.GEMINI_API_KEY)
    assert "super-secret-gemini-key" not in repr(settings.GEMINI_API_KEY)
    assert "super-secret-paypal-secret" not in str(settings.PAYPAL_CLIENT_SECRET)
    assert "super-secret-paypal-secret" not in repr(settings.PAYPAL_CLIENT_SECRET)
    assert "super-secret-channel3-key" not in str(settings.CHANNEL3_API_KEY)
    assert "super-secret-channel3-key" not in repr(settings.CHANNEL3_API_KEY)

    # Actual value accessible only via get_secret_value()
    assert settings.GEMINI_API_KEY.get_secret_value() == "super-secret-gemini-key"
    assert settings.CHANNEL3_API_KEY.get_secret_value() == "super-secret-channel3-key"


def test_sqlite_url_normalization():
    """Verify that relative SQLite paths are converted to stable absolute paths."""
    settings = Settings(DATABASE_URL="sqlite:///./test_custom.db")
    assert settings.DATABASE_URL.startswith("sqlite:///")
    assert "test_custom.db" in settings.DATABASE_URL
    assert not settings.DATABASE_URL.startswith("sqlite:///./")

"""Tests for outbound LLM PII redaction."""

from app.services.ai_content_sanitizer import P_DOC, P_EMAIL, P_HOST, P_IP, P_URL, redact_for_llm


def test_ip_and_fqdn() -> None:
    t = redact_for_llm("x 10.0.0.1 y server.corp.lan end")
    assert P_IP in t
    assert "10.0.0.1" not in t
    assert P_HOST in t
    assert "server.corp.lan" not in t


def test_url_and_email() -> None:
    t = redact_for_llm("u https://redmine.corp/issues/1 e a@b.co")
    assert P_URL in t
    assert P_EMAIL in t
    assert "redmine" not in t
    assert "a@b" not in t


def test_ru_patronymic() -> None:
    t = redact_for_llm("клиент Сидоров Алексей Петрович сказал")
    assert "[REDACTED:person]" in t
    assert "Сидоров" not in t

from __future__ import annotations

from email.message import EmailMessage

from backend.auth.notify import account_ready_message, send_account_ready_email


def test_account_ready_message_includes_the_temp_password(monkeypatch) -> None:
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)
    subject, body, link = account_ready_message(
        to_email="michael@example.com",
        name="Michael",
        temp_password="Admin",
    )
    assert "account is ready" in subject.lower()
    assert "https://faf-pricebook.fly.dev" in link
    assert "https://faf-pricebook.fly.dev" in body
    assert "Your temporary password is Admin." in body


def test_account_ready_message_omits_a_password_when_none_was_set(monkeypatch) -> None:
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)
    _subject, body, _link = account_ready_message(to_email="michael@example.com", name="Michael")
    assert "Your temporary password is" not in body


def test_invite_message_is_a_live_app_invite_link(monkeypatch) -> None:
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)
    _subject, body, link = account_ready_message(
        to_email="michael@example.com",
        name="Michael",
        invite_token="tok_abc",
    )
    assert link == "https://faf-pricebook.fly.dev/?invite=tok_abc"
    assert "invite=tok_abc" in body


def test_create_user_emails_the_live_app_link(tmp_path, monkeypatch) -> None:
    from backend.auth.bootstrap import bootstrap_users
    from backend.auth.store import AuthStore

    monkeypatch.setenv("ADMIN_EMAIL", "owner@faf.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-pass-1")
    sent: list[tuple[str, str, str | None]] = []

    def fake_send(**kwargs):
        sent.append(
            (
                kwargs.get("to_email"),
                kwargs.get("name"),
                kwargs.get("invite_token"),
                kwargs.get("temp_password"),
            )
        )
        return True

    monkeypatch.setattr("backend.auth.store.send_account_ready_email", fake_send)
    path = tmp_path / "app.db"
    bootstrap_users(path)
    store = AuthStore(path)
    admin = store.authenticate("owner@faf.example", "admin-pass-1")
    assert admin is not None
    store.create_user(
        actor=admin,
        email="michael@example.com",
        role="manager",
        password="Admin",
        name="Michael",
    )
    assert sent == [("michael@example.com", "Michael", None, "Admin")]


def test_send_account_ready_email_uses_injected_sender() -> None:
    sent: list[EmailMessage] = []
    ok = send_account_ready_email(
        to_email="michael@example.com",
        name="Michael",
        temp_password="Admin",
        sender=sent.append,
    )
    assert ok is True
    assert sent[0]["To"] == "michael@example.com"
    assert "faf-pricebook.fly.dev" in sent[0].get_content()
    assert "Your temporary password is Admin." in sent[0].get_content()

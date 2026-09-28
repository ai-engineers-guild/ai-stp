"""SMTP mail delivery: SmtpConfig mechanics, both mail ports, provider pick (#201)."""

from __future__ import annotations

from email.message import EmailMessage
from types import TracebackType

import pytest

from ai_stp_platform.corporate_mail import SmtpCorporateMailPort
from ai_stp_platform.mail import SmtpConfig, SmtpMailPort
from ai_stp_worker.__main__ import select_mail_provider
from ai_stp_worker.settings import WorkerSettings


class _FakeSmtpClient:
    """Records the calls SmtpConfig.send makes, in order."""

    def __init__(self, refuse: bool = False) -> None:
        self.ops: list[object] = []
        self.messages: list[EmailMessage] = []
        self.refuse = refuse

    def __enter__(self) -> _FakeSmtpClient:
        self.ops.append("connect")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.ops.append("quit")

    def starttls(self) -> None:
        self.ops.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.ops.append(("login", user, password))

    def send_message(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]:
        self.ops.append(msg)
        self.messages.append(msg)
        return {"r@x.test": (550, b"refused")} if self.refuse else {}


def _message() -> EmailMessage:
    message = EmailMessage()
    message["From"] = "inv@x.test"
    message["To"] = "a@b.c"
    message["Subject"] = "s"
    message.set_content("body")
    return message


def _config(client: _FakeSmtpClient, **kwargs: object) -> SmtpConfig:
    kwargs.setdefault("host", "relay.test")
    kwargs.setdefault("client_factory", lambda: client)
    return SmtpConfig(**kwargs)  # type: ignore[arg-type]


def test_smtp_plain_listener_sends_without_tls_or_login() -> None:
    client = _FakeSmtpClient()
    _config(client, port=1025, use_starttls=False).send(_message())
    assert client.ops[0] == "connect"
    assert len(client.messages) == 1
    assert client.ops[-1] == "quit"
    assert "starttls" not in client.ops
    assert not [op for op in client.ops if isinstance(op, tuple)]


def test_smtp_starttls_and_login_in_order() -> None:
    client = _FakeSmtpClient()
    _config(client, port=587, username="u", password="p").send(_message())
    assert client.ops[0:2] == ["connect", "starttls"]
    login_at = client.ops.index(("login", "u", "p"))
    assert login_at < client.ops.index(client.messages[0])


def test_smtp_implicit_tls_skips_starttls() -> None:
    client = _FakeSmtpClient()
    _config(client, port=465, use_tls=True, use_starttls=True).send(_message())
    assert "starttls" not in client.ops


def test_smtp_refused_recipient_raises() -> None:
    client = _FakeSmtpClient(refuse=True)
    cfg = SmtpConfig(
        host="relay.test",
        use_starttls=False,
        client_factory=lambda: client,
    )
    with pytest.raises(RuntimeError, match="refused"):
        cfg.send(_message())


def test_smtp_corporate_port_builds_message() -> None:
    client = _FakeSmtpClient()
    port = SmtpCorporateMailPort(
        smtp=_config(client, use_starttls=False),
        from_address="invitations@corp.test",
    )
    assert port.send_invitation(to_email="a@b.c", subject="Join Corp", text="Hi") is None
    message = client.messages[0]
    assert message["From"] == "invitations@corp.test"
    assert message["To"] == "a@b.c"
    assert message["Subject"] == "Join Corp"
    assert message.get_content() == "Hi\n"


def test_smtp_mail_port_carries_token_in_body_url_only() -> None:
    client = _FakeSmtpClient()
    port = SmtpMailPort(
        smtp=_config(client, use_starttls=False),
        from_address="noreply@x.test",
        accept_base_url="https://app.example/en",
    )
    port.send_invitation(
        to_email="a@b.c",
        invitation_id="invite_1",
        object_stable_id="obj",
        major=3,
        accept_token="secret-token",
    )
    message = client.messages[0]
    body = message.get_content()
    assert "https://app.example/en/invitations/invite_1#token=secret-token" in body
    # The bearer token stays out of headers — subject carries object id only.
    assert "secret-token" not in str(message["Subject"])
    assert "obj 3.*" in str(message["Subject"])


def _worker(**kwargs: object) -> WorkerSettings:
    return WorkerSettings(**kwargs)  # type: ignore[arg-type]


def test_provider_auto_defaults_to_recording() -> None:
    assert select_mail_provider(_worker()) == "recording"


def test_provider_auto_smtp_when_host_set() -> None:
    assert select_mail_provider(_worker(smtp_host="mailpit")) == "smtp"


def test_provider_auto_resend_key_beats_smtp_host() -> None:
    assert select_mail_provider(_worker(smtp_host="mailpit", resend_api_key="re_x")) == "resend"
    assert select_mail_provider(_worker(corporate_resend_api_key="re_x")) == "resend"


def test_provider_explicit_pin_wins() -> None:
    assert select_mail_provider(_worker(mail_provider="smtp")) == "smtp"
    assert select_mail_provider(_worker(mail_provider="recording", smtp_host="h")) == "recording"

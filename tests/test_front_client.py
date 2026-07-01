from __future__ import annotations

from sales_cockpit.config import get_settings
from sales_cockpit.services.front_client import FrontApiError, FrontClient


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        text: str = "",
        headers: dict | None = None,
        content: bytes = b"",
    ):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}
        self.content = content

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.calls = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_front_client_paginates_conversations() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "_results": [{"id": "cnv_1"}],
                    "_pagination": {"next": "https://api2.frontapp.com/conversations?page_token=next"},
                },
            ),
            FakeResponse(200, {"_results": [{"id": "cnv_2"}], "_pagination": {"next": None}}),
        ]
    )
    client = FrontClient(api_token="test", session=session)

    conversations = client.list_conversations()

    assert [item["id"] for item in conversations] == ["cnv_1", "cnv_2"]
    assert session.calls[0][1] == "https://api2.frontapp.com/conversations"
    assert session.calls[0][2]["params"]["limit"] == 100
    assert session.calls[1][1] == "https://api2.frontapp.com/conversations?page_token=next"
    assert session.calls[1][2]["params"] == {}


def test_front_client_stops_pagination_at_limit() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "_results": [{"id": "cnv_1"}],
                    "_pagination": {"next": "https://api2.frontapp.com/conversations?page_token=next"},
                },
            ),
            FakeResponse(200, {"_results": [{"id": "cnv_2"}], "_pagination": {"next": None}}),
        ]
    )
    client = FrontClient(api_token="test", session=session)

    conversations = client.list_conversations(limit=1)

    assert conversations == [{"id": "cnv_1"}]
    assert len(session.calls) == 1


def test_front_client_search_encodes_query() -> None:
    session = FakeSession([FakeResponse(200, {"_results": [], "_pagination": {"next": None}})])
    client = FrontClient(api_token="test", session=session)

    client.search_conversations('recipient:+41790000000 is:open')

    assert session.calls[0][1].endswith("/conversations/search/recipient%3A%2B41790000000%20is%3Aopen")


def test_front_client_lists_conversation_messages_oldest_first() -> None:
    session = FakeSession([FakeResponse(200, {"_results": [{"id": "msg_1"}], "_pagination": {"next": None}})])
    client = FrontClient(api_token="test", session=session)

    messages = client.list_conversation_messages("cnv_123")

    assert messages == [{"id": "msg_1"}]
    assert session.calls[0][1] == "https://api2.frontapp.com/conversations/cnv_123/messages"
    assert session.calls[0][2]["params"]["sort_by"] == "created_at"
    assert session.calls[0][2]["params"]["sort_order"] == "asc"


def test_front_client_requires_token_from_settings(monkeypatch) -> None:
    monkeypatch.delenv("SALES_COCKPIT_FRONT_API_TOKEN", raising=False)
    get_settings.cache_clear()

    try:
        FrontClient.from_settings()
    except FrontApiError as exc:
        assert "SALES_COCKPIT_FRONT_API_TOKEN" in str(exc)
    else:
        raise AssertionError("Front token should be required.")
    finally:
        get_settings.cache_clear()


def test_front_client_downloads_attachment_binary() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                payload=None,
                headers={
                    "Content-Type": "image/png",
                    "Content-Disposition": 'attachment; filename="qr-code.png"',
                },
                content=b"PNGDATA",
            )
        ]
    )
    client = FrontClient(api_token="test", session=session)

    attachment = client.download_attachment("https://api2.frontapp.com/download/att_1")

    assert attachment == {
        "content": b"PNGDATA",
        "mime_type": "image/png",
        "file_name": "qr-code.png",
    }
    assert session.calls[0][2]["headers"]["Accept"] == "*/*"


def test_front_client_retries_rate_limit_with_retry_after(monkeypatch) -> None:
    sleeps = []
    session = FakeSession(
        [
            FakeResponse(
                429,
                {"_error": {"message": "Rate limit exceeded."}},
                headers={"Retry-After": "0.1"},
            ),
            FakeResponse(200, {"_results": [{"id": "cnv_1"}], "_pagination": {"next": None}}),
        ]
    )
    monkeypatch.setattr("sales_cockpit.services.front_client.time.sleep", sleeps.append)
    client = FrontClient(api_token="test", session=session, max_retries=1)

    conversations = client.list_conversations(limit=1)

    assert conversations == [{"id": "cnv_1"}]
    assert len(session.calls) == 2
    assert sleeps == [0.1]


def test_front_client_retries_rate_limit_milliseconds_message(monkeypatch) -> None:
    sleeps = []
    session = FakeSession(
        [
            FakeResponse(
                429,
                {"_error": {"message": "Rate limit exceeded. Please retry in 250 milliseconds."}},
            ),
            FakeResponse(200, {"_results": [], "_pagination": {"next": None}}),
        ]
    )
    monkeypatch.setattr("sales_cockpit.services.front_client.time.sleep", sleeps.append)
    client = FrontClient(api_token="test", session=session, max_retries=1)

    assert client.list_conversations(limit=1) == []
    assert sleeps == [0.25]


def test_front_client_caps_retry_delay(monkeypatch) -> None:
    sleeps = []
    session = FakeSession(
        [
            FakeResponse(
                429,
                {"_error": {"message": "Rate limit exceeded. Please retry in 60000 milliseconds."}},
            ),
            FakeResponse(200, {"_results": [], "_pagination": {"next": None}}),
        ]
    )
    monkeypatch.setattr("sales_cockpit.services.front_client.time.sleep", sleeps.append)
    client = FrontClient(
        api_token="test",
        session=session,
        max_retries=1,
        max_retry_delay_seconds=2.0,
    )

    assert client.list_conversations(limit=1) == []
    assert sleeps == [2.0]

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class MockTwilioResult:
    sid: str
    status: str
    provider: str = "mock_twilio"


class MockTwilioClient:
    def send_freeform(
        self, to_phone: str, body: str, media_urls: list[str] | None = None
    ) -> MockTwilioResult:
        return MockTwilioResult(sid=f"SM_MOCK_{uuid4().hex[:24]}", status="sent")

    def send_template(
        self, to_phone: str, content_sid: str, variables: dict[str, str]
    ) -> MockTwilioResult:
        return MockTwilioResult(sid=f"SM_MOCK_{uuid4().hex[:24]}", status="sent")

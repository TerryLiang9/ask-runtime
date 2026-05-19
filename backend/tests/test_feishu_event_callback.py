import os
import tempfile
import unittest

import httpx

os.environ["EMATA_DATABASE_URL"] = "sqlite:///:memory:"

from app.integrations import TemporalRuntime
from app.main import create_app


class TestFallbackTemporalRuntime(TemporalRuntime):
    def __init__(self) -> None:
        super().__init__(target_hostport="temporal:7233", namespace="default")
        self.mode = "fallback"
        self.reason = "test_runtime"


def build_client() -> httpx.AsyncClient:
    tempdir = tempfile.mkdtemp(prefix="emata-feishu-event-")
    database_url = f"sqlite:///{os.path.join(tempdir, 'test.db')}"
    os.environ["EMATA_EMBEDDING_BASE_URL"] = ""
    os.environ["EMATA_EMBEDDING_API_KEY"] = ""
    os.environ["EMATA_MODEL_BASE_URL"] = ""
    os.environ["EMATA_MODEL_API_KEY"] = ""
    os.environ["EMATA_MODEL_NAME"] = ""
    app = create_app(
        database_url=database_url,
        temporal_runtime=TestFallbackTemporalRuntime(),
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


class FakeFeishuReplyClient:
    def __init__(self) -> None:
        self.replies = []

    def reply_to_message(self, *, message_id: str, text: str) -> dict:
        self.replies.append({"message_id": message_id, "text": text})
        return {"message_id": message_id}


class FeishuEventCallbackTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_feishu_url_verification_returns_challenge(self) -> None:
        client = build_client()

        response = await client.post(
            "/api/v1/feishu/events",
            json={"type": "url_verification", "challenge": "challenge-token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"challenge": "challenge-token"})
        await client.aclose()

    async def test_feishu_text_message_runs_ask_and_replies(self) -> None:
        client = build_client()
        reply_client = FakeFeishuReplyClient()
        client._transport.app.state.container.feishu_reply_client = reply_client

        response = await client.post(
            "/api/v1/feishu/events",
            json={
                "schema": "2.0",
                "header": {
                    "event_id": "evt-message-1",
                    "event_type": "im.message.receive_v1",
                },
                "event": {
                    "sender": {"sender_id": {"open_id": "ou_sender_1"}},
                    "message": {
                        "message_id": "om_message_1",
                        "chat_id": "oc_chat_1",
                        "message_type": "text",
                        "content": "{\"text\":\"hi\"}",
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "replied")
        self.assertEqual(payload["event_id"], "evt-message-1")
        self.assertEqual(len(reply_client.replies), 1)
        self.assertEqual(reply_client.replies[0]["message_id"], "om_message_1")
        self.assertTrue(reply_client.replies[0]["text"])
        await client.aclose()

    async def test_feishu_duplicate_event_is_ignored(self) -> None:
        client = build_client()
        reply_client = FakeFeishuReplyClient()
        client._transport.app.state.container.feishu_reply_client = reply_client
        payload = {
            "schema": "2.0",
            "header": {
                "event_id": "evt-message-dup",
                "event_type": "im.message.receive_v1",
            },
            "event": {
                "sender": {"sender_id": {"open_id": "ou_sender_1"}},
                "message": {
                    "message_id": "om_message_dup",
                    "chat_id": "oc_chat_dup",
                    "message_type": "text",
                    "content": "{\"text\":\"hi\"}",
                },
            },
        }

        first = await client.post("/api/v1/feishu/events", json=payload)
        second = await client.post("/api/v1/feishu/events", json=payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(len(reply_client.replies), 1)
        await client.aclose()


if __name__ == "__main__":
    unittest.main()

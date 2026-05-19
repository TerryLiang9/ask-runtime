import json
import os
from typing import Any, Dict, Optional

import httpx

from app.core import UserRecord


class FeishuReplyClient:
    def __init__(
        self,
        *,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        base_url: str = "https://open.feishu.cn/open-apis",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.app_id = app_id or os.getenv("EMATA_FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.getenv("EMATA_FEISHU_APP_SECRET", "")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._tenant_access_token = ""

    def reply_to_message(self, *, message_id: str, text: str) -> Dict[str, Any]:
        token = self._get_tenant_access_token()
        response = httpx.post(
            f"{self.base_url}/im/v1/messages/{message_id}/reply",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code", 0) not in {0, "0"}:
            raise RuntimeError(payload.get("msg") or "feishu_reply_failed")
        return payload.get("data", {})

    def _get_tenant_access_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        if not self.app_id or not self.app_secret:
            raise RuntimeError("missing_feishu_app_credentials")
        response = httpx.post(
            f"{self.base_url}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("tenant_access_token", "")
        if not token:
            raise RuntimeError(payload.get("msg") or "tenant_access_token_missing")
        self._tenant_access_token = token
        return token


class FeishuEventHandler:
    def __init__(self, container: Any, reply_client: FeishuReplyClient) -> None:
        self.container = container
        self.reply_client = reply_client
        self.seen_event_ids = set()

    def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        challenge = self._extract_challenge(payload)
        if challenge:
            return {"challenge": challenge}

        event_type = self._extract_event_type(payload)
        event_id = self._extract_event_id(payload)
        if event_id and event_id in self.seen_event_ids:
            return {"status": "duplicate", "event_id": event_id}
        if event_id:
            self.seen_event_ids.add(event_id)

        if event_type != "im.message.receive_v1":
            return {"status": "ignored", "event_type": event_type, "event_id": event_id}

        inbound = self._extract_text_message(payload)
        if not inbound:
            return {"status": "ignored", "reason": "unsupported_message", "event_id": event_id}

        user = self.container.get_current_user()
        session = self._get_or_create_session(user=user, chat_id=inbound["chat_id"])
        result = self.container.run_ask_turn(user, session.id, inbound["text"])
        answer = self._extract_reply_text(result) or "我已收到，但当前没有生成可发送的文本回复。"
        self.reply_client.reply_to_message(message_id=inbound["message_id"], text=answer)
        return {
            "status": "replied",
            "event_id": event_id,
            "message_id": inbound["message_id"],
            "session_id": session.id,
        }

    @staticmethod
    def _extract_challenge(payload: Dict[str, Any]) -> str:
        if payload.get("type") == "url_verification":
            return str(payload.get("challenge", ""))
        if payload.get("schema") == "2.0" and payload.get("challenge"):
            return str(payload.get("challenge", ""))
        return ""

    @staticmethod
    def _extract_event_type(payload: Dict[str, Any]) -> str:
        header = payload.get("header") or {}
        return str(header.get("event_type") or payload.get("event_type") or "")

    @staticmethod
    def _extract_event_id(payload: Dict[str, Any]) -> str:
        header = payload.get("header") or {}
        return str(header.get("event_id") or payload.get("event_id") or "")

    @staticmethod
    def _extract_text_message(payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
        event = payload.get("event") or {}
        message = event.get("message") or {}
        if message.get("message_type") != "text":
            return None
        message_id = str(message.get("message_id") or "")
        chat_id = str(message.get("chat_id") or "")
        text = FeishuEventHandler._parse_text_content(message.get("content"))
        if not message_id or not chat_id or not text:
            return None
        return {"message_id": message_id, "chat_id": chat_id, "text": text}

    @staticmethod
    def _parse_text_content(raw_content: Any) -> str:
        if isinstance(raw_content, dict):
            return str(raw_content.get("text", "")).strip()
        if not isinstance(raw_content, str):
            return ""
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            return raw_content.strip()
        if isinstance(parsed, dict):
            return str(parsed.get("text", "")).strip()
        return ""

    def _get_or_create_session(self, *, user: UserRecord, chat_id: str):
        for session in self.container.store.ask_sessions.values():
            context = session.active_context or {}
            if (
                session.user_id == user.id
                and session.organization_id == user.organization_id
                and context.get("feishu_chat_id") == chat_id
            ):
                return session
        return self.container.create_ask_session(
            user=user,
            skill_id="hr_recruiting",
            title=f"Feishu Chat {chat_id}",
            initial_context={
                "source": "feishu",
                "feishu_chat_id": chat_id,
            },
        )

    @staticmethod
    def _extract_reply_text(result: Dict[str, Any]) -> str:
        for output in result.get("outputs", []):
            if output.get("type") in {"message", "card"}:
                text = str(output.get("text", "")).strip()
                if text:
                    return text
        return ""

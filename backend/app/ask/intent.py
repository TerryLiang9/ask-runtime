from __future__ import annotations

from typing import Any, Dict


class AskIntentRouter:
    ACTION_MARKERS = (
        "安排",
        "发给",
        "发到",
        "发消息",
        "发信息",
        "发送",
        "通知",
        "创建",
        "约",
        "告诉",
        "开会",
        "会议",
        "日程",
        "邀请",
        "约个会",
    )
    KNOWLEDGE_MARKERS = (
        "多少",
        "是什么",
        "什么是",
        "怎么",
        "如何",
        "规则",
        "流程",
        "制度",
        "政策",
        "额度",
        "报销",
        "?",
        "？",
    )
    AMBIGUOUS_ACTION_MESSAGES = {
        "发给谁",
        "发给她",
        "发给他",
        "发给它",
        "发到群里",
        "通知一下",
        "通知一个人",
    }

    def route(self, *, message: str, active_context: Dict[str, Any]) -> Dict[str, Any]:
        content = (message or "").strip()
        lowered = content.lower()
        if not content:
            return {"route": "clarification"}
        if any(marker in content or marker in lowered for marker in self.ACTION_MARKERS):
            if content in self.AMBIGUOUS_ACTION_MESSAGES:
                return {"route": "clarification"}
            if ("刚才" in content or "上一轮" in content or "上一个" in content) and self._last_shareable_text(
                active_context
            ):
                return {"route": "answer_then_action"}
            return {"route": "action_only"}
        if any(marker in content or marker in lowered for marker in self.KNOWLEDGE_MARKERS):
            return {"route": "knowledge_qa"}
        return {"route": "skill_default"}

    @staticmethod
    def _last_shareable_text(active_context: Dict[str, Any]) -> str:
        working_context = active_context.get("working_context", {})
        return str(
            working_context.get("last_shareable_text")
            or active_context.get("last_shareable_text")
            or ""
        ).strip()

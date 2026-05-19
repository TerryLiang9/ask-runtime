from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class AskContextState:
    conversation_memory: Dict[str, Any] = field(default_factory=dict)
    working_context: Dict[str, Any] = field(default_factory=dict)
    pending_action_draft: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Dict[str, Any] | None) -> "AskContextState":
        state = cls()
        if not isinstance(value, dict):
            return state

        for section in AskContextManager.SECTION_KEYS:
            incoming = value.get(section)
            if isinstance(incoming, dict):
                getattr(state, section).update(incoming)

        for key, incoming in value.items():
            if key in AskContextManager.SECTION_KEYS:
                continue
            if key in AskContextManager.CONVERSATION_MEMORY_KEYS:
                state.conversation_memory[key] = incoming
            else:
                state.working_context[key] = incoming
        return state

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return {
            "conversation_memory": dict(self.conversation_memory),
            "working_context": dict(self.working_context),
            "pending_action_draft": dict(self.pending_action_draft),
        }

    def to_flat_dict(self) -> Dict[str, Any]:
        flattened: Dict[str, Any] = self.to_dict()
        flattened.update(self.conversation_memory)
        flattened.update(self.working_context)
        flattened["pending_action_draft"] = dict(self.pending_action_draft)
        return flattened


class AskContextManager:
    SECTION_KEYS = ("conversation_memory", "working_context", "pending_action_draft")
    CONVERSATION_MEMORY_KEYS = {
        "last_knowledge_query",
        "last_knowledge_hits",
        "last_knowledge_answer_mode",
        "last_knowledge_answer_text",
        "recent_messages",
    }
    DEFAULT_CONTEXT = {
        "conversation_memory": {},
        "working_context": {},
        "pending_action_draft": {},
    }

    def normalize(self, value: Dict[str, Any] | None) -> Dict[str, Dict[str, Any]]:
        normalized = deepcopy(self.DEFAULT_CONTEXT)
        normalized.update(AskContextState.from_mapping(value).to_dict())
        return normalized

    def apply_patch(self, current: Dict[str, Any] | None, patch: Dict[str, Any] | None) -> Dict[str, Any]:
        merged = self.normalize(current)
        incoming = self.normalize(patch)

        merged["conversation_memory"].update(incoming["conversation_memory"])
        merged["working_context"].update(incoming["working_context"])
        if isinstance(patch, dict) and "pending_action_draft" in patch:
            merged["pending_action_draft"] = dict(incoming["pending_action_draft"])
        else:
            merged["pending_action_draft"].update(incoming["pending_action_draft"])

        return self.flatten(merged)

    def flatten(self, normalized: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        return AskContextState(
            conversation_memory=dict(normalized.get("conversation_memory", {})),
            working_context=dict(normalized.get("working_context", {})),
            pending_action_draft=dict(normalized.get("pending_action_draft", {})),
        ).to_flat_dict()

import unittest

from app.ask_context import AskContextManager, AskContextState


class AskContextManagerTestCase(unittest.TestCase):
    def test_context_state_maps_flat_fields_to_sections(self) -> None:
        state = AskContextState.from_mapping(
            {
                "last_knowledge_query": "报销额度是多少",
                "last_shareable_text": "报销额度是 3000 元",
                "pending_action_draft": {"intent": "message.send"},
            }
        )

        self.assertEqual(state.conversation_memory["last_knowledge_query"], "报销额度是多少")
        self.assertEqual(state.working_context["last_shareable_text"], "报销额度是 3000 元")
        self.assertEqual(state.pending_action_draft["intent"], "message.send")
        self.assertEqual(
            state.to_dict(),
            {
                "conversation_memory": {"last_knowledge_query": "报销额度是多少"},
                "working_context": {"last_shareable_text": "报销额度是 3000 元"},
                "pending_action_draft": {"intent": "message.send"},
            },
        )
        self.assertEqual(state.to_flat_dict()["last_shareable_text"], "报销额度是 3000 元")

    def test_apply_patch_separates_conversation_working_and_pending(self) -> None:
        manager = AskContextManager()
        current = {
            "conversation_memory": {"recent_messages": ["old"]},
            "working_context": {"last_target": "Ai应用开发群"},
            "pending_action_draft": {"intent": "message.send"},
        }

        patched = manager.apply_patch(
            current,
            {
                "conversation_memory": {"recent_messages": ["new"]},
                "working_context": {"last_shareable_text": "你好"},
                "pending_action_draft": {},
            },
        )

        self.assertEqual(patched["conversation_memory"]["recent_messages"], ["new"])
        self.assertEqual(patched["working_context"]["last_target"], "Ai应用开发群")
        self.assertEqual(patched["working_context"]["last_shareable_text"], "你好")
        self.assertEqual(patched["pending_action_draft"], {})


if __name__ == "__main__":
    unittest.main()

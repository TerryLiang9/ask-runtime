import unittest

import app.ask_intent as ask_intent_module
import app.ask_runtime as ask_runtime_module
from app.ask_intent import AskIntentRouter


class AskIntentRouterModuleTestCase(unittest.TestCase):
    def test_runtime_reuses_router_from_intent_module(self) -> None:
        self.assertIs(ask_runtime_module.AskIntentRouter, AskIntentRouter)

    def test_intent_module_only_owns_intent_routing(self) -> None:
        self.assertFalse(hasattr(ask_intent_module, "AskRuntime"))
        self.assertFalse(hasattr(ask_intent_module, "AskKnowledgeQaModule"))
        self.assertFalse(hasattr(ask_intent_module, "AskPolicyEngine"))

    def test_prefers_action_when_message_contains_explicit_send_intent(self) -> None:
        router = AskIntentRouter()
        result = router.route(
            message="给李雷发送“你好”",
            active_context={"pending_action_draft": {}},
        )
        self.assertEqual(result["route"], "action_only")

    def test_routes_previous_answer_plus_send_to_answer_then_action(self) -> None:
        router = AskIntentRouter()
        result = router.route(
            message="把刚才的结论发到 Ai应用开发群",
            active_context={
                "working_context": {"last_shareable_text": "报销额度是 3000 元"},
            },
        )
        self.assertEqual(result["route"], "answer_then_action")


if __name__ == "__main__":
    unittest.main()

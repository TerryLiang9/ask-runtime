import json
import os
import tempfile
import unittest
from unittest.mock import patch

import httpx

from app.auth import AuthSettings, create_session_token
from app.core import KnowledgeDocumentRecord
from app.integrations import TemporalRuntime
from app.main import create_app


class TestFallbackTemporalRuntime(TemporalRuntime):
    def __init__(self) -> None:
        super().__init__(target_hostport="temporal:7233", namespace="default")
        self.mode = "fallback"
        self.reason = "test_runtime"


def build_client() -> httpx.AsyncClient:
    tempdir = tempfile.mkdtemp(prefix="emata-api-")
    database_url = f"sqlite:///{os.path.join(tempdir, 'test.db')}"
    app = create_app(
        database_url=database_url,
        temporal_runtime=TestFallbackTemporalRuntime(),
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def build_auth_env() -> dict:
    password_hash = "pbkdf2_sha256$120000$test-salt$_g2hp9NUfKMKp7ob7co7DUe7IPW-o9z2ZXQTMddU6-s"
    users = [
        {
            "id": "user-admin",
            "organization_id": "org-acme",
            "username": "admin",
            "display_name": "EMATA Admin",
            "password_hash": password_hash,
            "role_bindings": [
                {
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-finance",
                    "role": "workspace_admin",
                },
                {
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-sales",
                    "role": "workspace_admin",
                },
            ],
        }
    ]
    return {
        "EMATA_AUTH_ENABLED": "true",
        "EMATA_SESSION_SECRET": "test-session-secret-with-enough-length",
        "EMATA_SESSION_TTL_SECONDS": "3600",
        "EMATA_AUTH_COOKIE_SECURE": "false",
        "EMATA_BOOTSTRAP_USERS_JSON": json.dumps(users),
        "EMATA_MODEL_API_KEY": "test-model-key",
        "EMATA_RERANK_API_KEY": "test-rerank-key",
        "EMATA_EMBEDDING_API_KEY": "test-embedding-key",
        "EMATA_INTERNAL_API_KEY": "test-internal-key",
    }


class ApiContractTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_auth_login_sets_session_cookie_and_me_uses_authenticated_user(self) -> None:
        with patch.dict(os.environ, build_auth_env(), clear=False):
            client = build_client()

            login_response = await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "secret-pass"},
            )

            self.assertEqual(login_response.status_code, 200)
            self.assertIn("emata_session", client.cookies)
            payload = login_response.json()
            self.assertEqual(payload["user"]["id"], "user-admin")
            self.assertTrue(payload["expires_at"])

            me_response = await client.get("/api/v1/me")

            self.assertEqual(me_response.status_code, 200)
            self.assertEqual(me_response.json()["username"], "admin")
            await client.aclose()

    async def test_auth_login_rejects_invalid_password_without_cookie(self) -> None:
        with patch.dict(os.environ, build_auth_env(), clear=False):
            client = build_client()

            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "wrong-pass"},
            )

            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "invalid_credentials")
            self.assertNotIn("emata_session", client.cookies)
            await client.aclose()

    async def test_auth_enabled_requires_cookie_for_public_api(self) -> None:
        with patch.dict(os.environ, build_auth_env(), clear=False):
            client = build_client()

            endpoints = [
                await client.get("/api/v1/me"),
                await client.get("/api/v1/workspaces"),
                await client.post("/api/v1/ask/sessions", json={"skill_id": "hr_recruiting"}),
                await client.get(
                    "/api/v1/knowledge/search",
                    params={"workspace_id": "workspace-finance", "query": "policy"},
                ),
            ]

            self.assertTrue(all(response.status_code == 401 for response in endpoints))
            self.assertTrue(all(response.json()["detail"] == "unauthenticated" for response in endpoints))
            await client.aclose()

    async def test_auth_rejects_tampered_session_cookie(self) -> None:
        with patch.dict(os.environ, build_auth_env(), clear=False):
            client = build_client()

            response = await client.get(
                "/api/v1/me",
                headers={"Cookie": "emata_session=tampered-token"},
            )

            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "unauthenticated")
            await client.aclose()

    async def test_auth_rejects_expired_session_cookie(self) -> None:
        with patch.dict(os.environ, build_auth_env(), clear=False):
            client = build_client()
            expired_settings = AuthSettings(
                enabled=True,
                session_secret="test-session-secret-with-enough-length",
                session_ttl_seconds=-1,
                cookie_secure=False,
            )
            expired_token, _expires_at = create_session_token("user-admin", expired_settings)

            response = await client.get(
                "/api/v1/me",
                headers={"Cookie": f"emata_session={expired_token}"},
            )

            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "unauthenticated")
            await client.aclose()

    async def test_auth_logout_clears_session_cookie(self) -> None:
        with patch.dict(os.environ, build_auth_env(), clear=False):
            client = build_client()
            await client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "secret-pass"},
            )

            logout_response = await client.post("/api/v1/auth/logout")
            me_response = await client.get("/api/v1/me")

            self.assertEqual(logout_response.status_code, 200)
            self.assertEqual(me_response.status_code, 401)
            await client.aclose()

    async def test_logout_marks_demo_mode_signed_out_when_auth_is_disabled(self) -> None:
        client = build_client()

        response = await client.post("/api/v1/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.cookies.get("emata_demo_signed_out"), "1")
        await client.aclose()

    async def test_auth_enabled_requires_bootstrap_users(self) -> None:
        env = build_auth_env()
        env["EMATA_BOOTSTRAP_USERS_JSON"] = "[]"
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaisesRegex(RuntimeError, "auth_not_configured"):
                build_client()

    async def test_internal_routes_require_key_when_configured(self) -> None:
        with patch.dict(os.environ, {"EMATA_INTERNAL_API_KEY": "test-internal-key"}, clear=False):
            client = build_client()

            response = await client.post(
                "/internal/feishu/events",
                json={
                    "event_type": "run_waiting_approval",
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-finance",
                    "run_id": "run-demo",
                    "approval_id": "approval-demo",
                    "targets": {"group_chat_ids": ["chat-finance"], "user_open_ids": []},
                    "payload": {"title": "Needs approval"},
                },
            )

            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "internal_unauthorized")
            await client.aclose()

    async def test_internal_routes_accept_configured_key(self) -> None:
        with patch.dict(os.environ, {"EMATA_INTERNAL_API_KEY": "test-internal-key"}, clear=False):
            client = build_client()

            response = await client.post(
                "/internal/feishu/events",
                headers={"X-EMATA-INTERNAL-KEY": "test-internal-key"},
                json={
                    "event_type": "run_waiting_approval",
                    "organization_id": "org-acme",
                    "workspace_id": "workspace-finance",
                    "run_id": "run-demo",
                    "approval_id": "approval-demo",
                    "targets": {"group_chat_ids": ["chat-finance"], "user_open_ids": []},
                    "payload": {"title": "Needs approval"},
                },
            )

            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["status"], "QUEUED")
            await client.aclose()

    async def test_me_endpoint_does_not_eagerly_require_storage_backend(self) -> None:
        with patch.dict(os.environ, {"EMATA_STORAGE_BACKEND": "minio"}, clear=False):
            client = build_client()

            response = await client.get("/api/v1/me")

            self.assertEqual(response.status_code, 200)
            await client.aclose()

    async def test_get_me_returns_local_rbac_identity_and_memberships(self) -> None:
        client = build_client()

        response = await client.get("/api/v1/me")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], "user-admin")
        self.assertEqual(payload["organization_id"], "org-acme")
        self.assertEqual(
            {binding["workspace_id"] for binding in payload["role_bindings"]},
            {"workspace-finance", "workspace-sales"},
        )
        await client.aclose()

    async def test_list_workspaces_is_scoped_to_current_organization(self) -> None:
        client = build_client()

        response = await client.get("/api/v1/workspaces")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["id"] for item in payload["items"]],
            ["workspace-finance", "workspace-sales"],
        )
        await client.aclose()

    async def test_cors_preflight_allows_local_console_origin(self) -> None:
        client = build_client()

        response = await client.options(
            "/api/v1/knowledge/search",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )
        await client.aclose()

    async def test_cors_preflight_allows_alternate_local_dev_port(self) -> None:
        client = build_client()

        response = await client.options(
            "/api/v1/ask/sessions",
            headers={
                "Origin": "http://127.0.0.1:3001",
                "Access-Control-Request-Method": "POST",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://127.0.0.1:3001",
        )
        await client.aclose()

    async def test_high_risk_run_requires_approval_and_can_be_approved(self) -> None:
        client = build_client()

        create_response = await client.post(
            "/api/v1/runs",
            json={
                "workspace_id": "workspace-finance",
                "title": "Sync ERP order update",
                "goal": "Push the approved order change into ERP.",
                "requested_capability": "erp.write",
            },
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["status"], "WAITING_APPROVAL")
        self.assertTrue(created["approval_request_id"])

        approval_response = await client.post(
            f"/api/v1/runs/{created['id']}/approve",
            json={"decision": "approve", "comment": "approved for rollout"},
        )

        self.assertEqual(approval_response.status_code, 200)
        approved = approval_response.json()
        self.assertEqual(approved["status"], "RUNNING")
        self.assertEqual(approved["approval"]["status"], "APPROVED")
        await client.aclose()

    async def test_list_runs_returns_created_runs_for_current_workspace_scope(self) -> None:
        client = build_client()

        await client.post(
            "/api/v1/runs",
            json={
                "workspace_id": "workspace-finance",
                "title": "Generate approval summary",
                "goal": "Create a pending approvals summary.",
                "requested_capability": "report.generate",
            },
        )

        response = await client.get("/api/v1/runs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["workspace_id"], "workspace-finance")
        self.assertEqual(payload["items"][0]["status"], "RUNNING")
        await client.aclose()

    async def test_knowledge_search_returns_workspace_private_and_shared_documents_only(self) -> None:
        client = build_client()

        response = await client.get(
            "/api/v1/knowledge/search",
            params={"workspace_id": "workspace-finance", "query": "policy"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("trace", payload)
        self.assertIn("backend_mode", payload["trace"])
        self.assertIn("query_variants", payload["trace"])
        self.assertIn("result_count", payload["trace"])
        self.assertGreaterEqual(len(payload["trace"]["query_variants"]), 1)
        first_item = payload["items"][0]
        self.assertIn("chunk_id", first_item)
        self.assertIn("block_type", first_item)
        self.assertIn("section_path", first_item)
        self.assertIn("matched_terms", first_item)
        self.assertIn("matched_query", first_item)
        self.assertIn("parser_backend", first_item)
        self.assertIn(first_item["block_type"], {"legacy_document", None})
        self.assertGreaterEqual(len(first_item["matched_terms"]), 1)
        self.assertIn(first_item["matched_query"], payload["trace"]["query_variants"])
        self.assertEqual(first_item["parser_backend"], "manual")
        self.assertTrue(all("chunk" in item["chunk_id"] for item in payload["items"]))
        filenames = [item["title"] for item in payload["items"]]
        self.assertIn("Finance Expense Policy", filenames)
        self.assertIn("Company Shared Policy", filenames)
        self.assertNotIn("Sales Battlecard", filenames)
        await client.aclose()

    async def test_knowledge_index_status_reports_backend_mode_collection_and_endpoint(self) -> None:
        tempdir = tempfile.mkdtemp(prefix="emata-api-")
        database_url = f"sqlite:///{os.path.join(tempdir, 'test.db')}"
        app = create_app(
            database_url=database_url,
            temporal_runtime=TestFallbackTemporalRuntime(),
        )
        app.state.container.knowledge_index.mode = "sdk"
        app.state.container.knowledge_index.reason = "available"
        app.state.container.knowledge_index.collection_name = "emata_documents"
        app.state.container.knowledge_index.uri = "http://127.0.0.1:19530"
        app.state.container.knowledge_index._collection_ready = True
        app.state.container.knowledge_index.records = {}
        app.state.container.knowledge_index.records["chunk-1"] = {
            "document_id": "chunk-1",
            "title": "Policy",
            "content": "Policy content",
            "metadata": {},
        }
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

        response = await client.get("/api/v1/knowledge/index/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["backend_mode"], "sdk")
        self.assertEqual(payload["backend_reason"], "available")
        self.assertEqual(payload["collection_name"], "emata_documents")
        self.assertEqual(payload["collection_ready"], True)
        self.assertEqual(payload["indexed_record_count"], 1)
        self.assertEqual(payload["endpoint"], "127.0.0.1:19530")
        await client.aclose()

    async def test_knowledge_search_exposes_chunk_location_and_parser_explanation_fields(self) -> None:
        tempdir = tempfile.mkdtemp(prefix="emata-api-")
        database_url = f"sqlite:///{os.path.join(tempdir, 'test.db')}"
        app = create_app(
            database_url=database_url,
            temporal_runtime=TestFallbackTemporalRuntime(),
        )
        app.state.container.knowledge_index.upsert_chunk(
            chunk_id="upload-finance-policy-chunk-0",
            title="Finance Approval Policy",
            content="Expense approval requires ERP review and finance authorization.",
            metadata={
                "organization_id": "org-acme",
                "workspace_id": "workspace-finance",
                "scope": "workspace",
                "block_type": "paragraph",
                "section_path": ["Approval Flow"],
                "page_number": 2,
                "page_end": 4,
                "parser": "mineru",
            },
        )
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

        response = await client.get(
            "/api/v1/knowledge/search",
            params={"workspace_id": "workspace-finance", "query": "expense approval ERP"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        first_item = payload["items"][0]
        self.assertEqual(first_item["page_number"], 2)
        self.assertEqual(first_item["page_end"], 4)
        self.assertEqual(first_item["parser_backend"], "mineru")
        self.assertIn("erp", [term.lower() for term in first_item["matched_terms"]])
        await client.aclose()

    async def test_knowledge_search_trace_reports_document_store_when_service_fallback_is_used(self) -> None:
        tempdir = tempfile.mkdtemp(prefix="emata-api-")
        database_url = f"sqlite:///{os.path.join(tempdir, 'test.db')}"
        app = create_app(
            database_url=database_url,
            temporal_runtime=TestFallbackTemporalRuntime(),
        )
        app.state.container.store.documents["doc-legacy"] = KnowledgeDocumentRecord(
            id="doc-legacy",
            organization_id="org-acme",
            workspace_id="workspace-finance",
            scope="workspace",
            title="Legacy Finance Policy",
            content="Legacy reimbursement fallback content.",
        )
        app.state.container.store.save_document(app.state.container.store.documents["doc-legacy"])
        app.state.container.knowledge_index.search_with_trace = lambda **kwargs: {
            "items": [],
            "trace": {
                "backend_mode": "sdk",
                "backend_reason": "available",
                "query_variants": [kwargs["query"]],
                "result_count": 0,
                "rewrite_applied": False,
            },
        }
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

        response = await client.get(
            "/api/v1/knowledge/search",
            params={"workspace_id": "workspace-finance", "query": "Legacy reimbursement"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["trace"]["backend_mode"], "document-store")
        self.assertEqual(payload["trace"]["backend_reason"], "legacy_document_fallback")
        self.assertEqual(payload["trace"]["result_count"], 1)
        self.assertEqual(payload["items"][0]["title"], "Legacy Finance Policy")
        self.assertGreaterEqual(len(payload["items"][0]["matched_terms"]), 1)
        self.assertIn(payload["items"][0]["matched_query"], payload["trace"]["query_variants"])
        await client.aclose()

    async def test_internal_feishu_event_enqueues_delivery_job(self) -> None:
        client = build_client()

        response = await client.post(
            "/internal/feishu/events",
            json={
                "event_type": "run_waiting_approval",
                "organization_id": "org-acme",
                "workspace_id": "workspace-finance",
                "run_id": "run-demo",
                "approval_id": "approval-demo",
                "targets": {
                    "group_chat_ids": ["chat-finance"],
                    "user_open_ids": ["ou_admin"],
                },
                "payload": {
                    "title": "ERP sync needs approval",
                    "summary": "Order 1001 is waiting for approval.",
                    "deeplink": "https://emata.local/runs/run-demo",
                },
            },
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "QUEUED")
        self.assertEqual(payload["channel"], "feishu")
        await client.aclose()

    async def test_run_memory_turns_can_be_recorded_and_read_back(self) -> None:
        client = build_client()

        create_response = await client.post(
            "/api/v1/runs",
            json={
                "workspace_id": "workspace-finance",
                "title": "Investigate reimbursement policy",
                "goal": "Answer the reimbursement policy question.",
                "requested_capability": "report.generate",
            },
        )
        run_id = create_response.json()["id"]

        append_response = await client.post(
            f"/api/v1/runs/{run_id}/memory/turns",
            json={
                "role": "user",
                "content": "审批人是 finance-manager，输出语言是中文。",
                "facts": [
                    {"key": "approver", "value": "finance-manager"},
                    {"key": "language", "value": "zh-CN"},
                ],
            },
        )

        self.assertEqual(append_response.status_code, 201)

        read_response = await client.get(f"/api/v1/runs/{run_id}/memory")

        self.assertEqual(read_response.status_code, 200)
        payload = read_response.json()
        self.assertEqual(payload["run_id"], run_id)
        self.assertEqual(payload["total_turns"], 1)
        self.assertEqual(payload["facts"][0]["key"], "approver")
        self.assertEqual(payload["recent_turns"][0]["content"], "审批人是 finance-manager，输出语言是中文。")
        await client.aclose()

    async def test_run_memory_compresses_older_turns_into_summary(self) -> None:
        client = build_client()

        create_response = await client.post(
            "/api/v1/runs",
            json={
                "workspace_id": "workspace-finance",
                "title": "Prepare approval brief",
                "goal": "Prepare an approval brief with context memory.",
                "requested_capability": "report.generate",
            },
        )
        run_id = create_response.json()["id"]

        turns = [
            "用户要求中文输出。",
            "需要结合共享制度和财务制度。",
            "审批人是 finance-director。",
            "重点关注 ERP 写入风险。",
            "如果信息不足要明确列出缺口。",
        ]
        for content in turns:
            await client.post(
                f"/api/v1/runs/{run_id}/memory/turns",
                json={"role": "user", "content": content, "facts": []},
            )

        read_response = await client.get(f"/api/v1/runs/{run_id}/memory")

        self.assertEqual(read_response.status_code, 200)
        payload = read_response.json()
        self.assertEqual(payload["total_turns"], 5)
        self.assertTrue(payload["summary"])
        self.assertLessEqual(len(payload["recent_turns"]), 3)
        self.assertIn("用户要求中文输出", payload["summary"])
        await client.aclose()


if __name__ == "__main__":
    unittest.main()

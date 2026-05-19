import test from "node:test";
import assert from "node:assert/strict";

import {
  ASK_COMMAND_TIMEOUT_MS,
  ASK_TURN_TIMEOUT_MS,
  buildLoginPayload,
  buildAskJobEventsUrl,
  buildAskJobStatusUrl,
  shouldUseApiFallbacks,
  resolveApiBaseUrl,
} from "../lib/api.js";

test("resolveApiBaseUrl trims trailing whitespace and slash", () => {
  assert.equal(
    resolveApiBaseUrl({
      NEXT_PUBLIC_EMATA_API_BASE_URL: "http://127.0.0.1:8000 /",
    }),
    "http://127.0.0.1:8000",
  );
});

test("resolveApiBaseUrl falls back to localhost when env is empty", () => {
  assert.equal(resolveApiBaseUrl({}), "http://localhost:8000");
});

test("resolveApiBaseUrl prefers server internal URL during SSR", () => {
  assert.equal(
    resolveApiBaseUrl(
      {
        EMATA_API_BASE_URL: "http://api:8000",
        NEXT_PUBLIC_EMATA_API_BASE_URL: "https://public.example",
      },
      { isServer: true },
    ),
    "http://api:8000",
  );
  assert.equal(
    resolveApiBaseUrl(
      {
        EMATA_API_BASE_URL: "http://api:8000",
        NEXT_PUBLIC_EMATA_API_BASE_URL: "https://public.example",
      },
      { isServer: false },
    ),
    "https://public.example",
  );
});

test("ask timeouts leave more room for real feishu round trips", () => {
  assert.equal(ASK_TURN_TIMEOUT_MS, 60000);
  assert.equal(ASK_COMMAND_TIMEOUT_MS, 120000);
});

test("ask job helper builds status and events urls", () => {
  assert.equal(
    buildAskJobStatusUrl("job_123"),
    "http://localhost:8000/api/v1/ask/jobs/job_123",
  );
  assert.equal(
    buildAskJobEventsUrl("job_123"),
    "http://localhost:8000/api/v1/ask/jobs/job_123/events",
  );
});

test("buildLoginPayload trims username and keeps password unchanged", () => {
  assert.deepEqual(buildLoginPayload({ username: " admin ", password: " secret pass " }), {
    username: "admin",
    password: " secret pass ",
  });
});

test("api fallbacks are disabled in production by default", () => {
  assert.equal(shouldUseApiFallbacks({ NODE_ENV: "production" }), false);
  assert.equal(shouldUseApiFallbacks({ NODE_ENV: "development" }), true);
  assert.equal(
    shouldUseApiFallbacks({
      NODE_ENV: "development",
      NEXT_PUBLIC_EMATA_DISABLE_API_FALLBACKS: "true",
    }),
    false,
  );
});

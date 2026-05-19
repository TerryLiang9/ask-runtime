import test from "node:test";
import assert from "node:assert/strict";

import { resolveApiBaseUrl } from "../lib/api.js";

test("resolveApiBaseUrl falls back to browser origin on the client", () => {
  globalThis.window = { location: { origin: "http://8.163.90.137" } };
  try {
    assert.equal(resolveApiBaseUrl({}, { isServer: false }), "http://8.163.90.137");
  } finally {
    delete globalThis.window;
  }
});


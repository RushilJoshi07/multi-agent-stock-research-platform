import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

if (!process.versions.node.startsWith("24.")) {
  throw new Error(`Fathom web tests need Node 24.x (see .nvmrc); this is ${process.versions.node}`);
}

// The browser-side version of pytest-socket: a test that forgets to mock fetch fails
// instead of making a real request.
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      throw new Error(`unmocked fetch in test: ${String(input)}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

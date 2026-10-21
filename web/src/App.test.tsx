// UI smoke test. fetch is mocked on purpose: this checks that each health state renders
// correctly. Whether the real API answers is covered by the Python tests and the step 5 gate.
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

function respondWith(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

describe("App", () => {
  it("renders the Fathom heading while the check is in flight", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));

    render(<App />);

    expect(screen.getByRole("heading", { name: "Fathom" })).toBeTruthy();
    expect(screen.getByText("Checking API…")).toBeTruthy();
  });

  it("shows healthy with the Postgres version on 200", async () => {
    respondWith(200, {
      status: "ok",
      checks: {
        postgres: { ok: true, version: "16.14", latency_ms: 2.1 },
        redis: { ok: true, latency_ms: 0.6 },
      },
    });

    render(<App />);

    expect(await screen.findByText("API healthy · Postgres 16.14")).toBeTruthy();
  });

  it("shows degraded with the failing service's error on 503", async () => {
    respondWith(503, {
      status: "degraded",
      checks: {
        postgres: { ok: true, version: "16.14", latency_ms: 2.0 },
        redis: { ok: false, error: "ConnectionError: Error 61 connecting to localhost:6380" },
      },
    });

    render(<App />);

    expect(await screen.findByText("API degraded")).toBeTruthy();
    expect(
      screen.getByText("redis: ConnectionError: Error 61 connecting to localhost:6380"),
    ).toBeTruthy();
    expect(screen.queryByText(/^postgres:/)).toBeNull();
  });

  it("shows unreachable with the status when the proxy returns 502", async () => {
    // What Vite's proxy returns when nothing listens on the API port (seen in step 4).
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("", { status: 502 })),
    );

    render(<App />);

    expect(await screen.findByText("API unreachable (HTTP 502)")).toBeTruthy();
  });

  it("shows unreachable when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    render(<App />);

    expect(await screen.findByText("API unreachable")).toBeTruthy();
  });
});

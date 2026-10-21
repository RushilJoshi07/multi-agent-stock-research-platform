// Shape of GET /health from src/api/routes/health.py.
export type ServiceCheck = {
  ok: boolean;
  version?: string;
  latency_ms?: number;
  error?: string;
};

export type HealthBody = {
  status: "ok" | "degraded";
  checks: Record<string, ServiceCheck>;
};

export type HealthResult =
  | { kind: "healthy"; body: HealthBody }
  | { kind: "degraded"; body: HealthBody }
  | { kind: "unreachable"; status: number | null; detail: string };

// Anything other than a well-formed 200 or 503 is "unreachable", never healthy.
export async function fetchHealth(): Promise<HealthResult> {
  let response: Response;
  try {
    response = await fetch("/api/health");
  } catch (error) {
    return { kind: "unreachable", status: null, detail: String(error) };
  }

  if (response.status !== 200 && response.status !== 503) {
    return { kind: "unreachable", status: response.status, detail: `HTTP ${response.status}` };
  }

  let body: HealthBody;
  try {
    body = (await response.json()) as HealthBody;
  } catch {
    return { kind: "unreachable", status: response.status, detail: "response was not JSON" };
  }
  if (typeof body?.checks !== "object" || body.checks === null) {
    return { kind: "unreachable", status: response.status, detail: "unexpected response shape" };
  }

  return response.status === 200 ? { kind: "healthy", body } : { kind: "degraded", body };
}

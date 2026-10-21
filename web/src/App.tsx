import { useCallback, useEffect, useState } from "react";
import { fetchHealth, type HealthResult } from "./health";

export default function App() {
  const [result, setResult] = useState<HealthResult | null>(null);

  const check = useCallback(() => {
    setResult(null);
    fetchHealth().then(setResult);
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  return (
    <main>
      <h1>Fathom</h1>
      <HealthStatus result={result} />
      <button type="button" onClick={check} disabled={result === null}>
        Check again
      </button>
    </main>
  );
}

function HealthStatus({ result }: { result: HealthResult | null }) {
  if (result === null) {
    return <p>Checking API…</p>;
  }
  if (result.kind === "unreachable") {
    return <p>API unreachable{result.status !== null ? ` (HTTP ${result.status})` : ""}</p>;
  }
  if (result.kind === "healthy") {
    const version = result.body.checks.postgres?.version ?? "version unavailable";
    return <p>API healthy · Postgres {version}</p>;
  }
  const failing = Object.entries(result.body.checks).filter(([, check]) => !check.ok);
  return (
    <div>
      <p>API degraded</p>
      <ul>
        {failing.map(([name, check]) => (
          <li key={name}>
            {name}: {check.error ?? "no error message"}
          </li>
        ))}
      </ul>
    </div>
  );
}

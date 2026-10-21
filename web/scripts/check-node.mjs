// Runs before lint, typecheck, test and build (the npm "pre" scripts). npm only checks
// "engines" on install, so this stops a run on the wrong Node major. See .nvmrc.
const required = "24";
const actual = process.versions.node;

if (actual.split(".")[0] !== required) {
  console.error(
    `Fathom web needs Node ${required}.x (see .nvmrc); this is Node ${actual}.\n` +
      `Run with: PATH="$HOME/.local/node/v24.21.0/bin:$PATH" npm ...`,
  );
  process.exit(1);
}

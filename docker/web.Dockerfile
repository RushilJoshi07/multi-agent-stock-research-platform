# Local development image for the React app. Node matches .nvmrc (docs/decisions/0007).
FROM node:24.21.0-bookworm-slim

WORKDIR /app

# Linux binaries (rolldown, oxlint, Tailwind's CSS engine) are installed here from the
# lockfile; compose keeps them in a volume so the Mac's node_modules never replaces them.
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci

# --host: Vite listens only on localhost by default, which the published port can't reach.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

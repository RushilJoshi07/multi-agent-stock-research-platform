# Local development image for the React app. Node matches .nvmrc (docs/decisions/0007).
FROM node:24.21.0-bookworm-slim

WORKDIR /app

# Dependencies first, as their own cached layer. npm ci installs the Linux builds of the
# platform-specific packages (rolldown, oxlint, Tailwind's CSS engine) from the lockfile.
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci

# Then the config and source. .dockerignore keeps the Mac's web/node_modules out. Compose
# bind-mounts only web/src and web/index.html over these, so node_modules and the config
# files always come from this image; changing them rebuilds it through `make up` (--build).
COPY web/ ./

# --host: Vite listens only on localhost by default, which the published port can't reach.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

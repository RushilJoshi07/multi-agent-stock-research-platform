# Local development image for the FastAPI app. Python and uv versions match .python-version
# and the local uv (docs/decisions/0001, 0003).
FROM python:3.13.16-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

# The venv lives outside /app so the ./src bind mount can't hide it. Use the image's Python,
# never a downloaded one.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first, as their own cached layer. --locked fails if uv.lock is out of date.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

# Then the project itself (installed editable, so the bind-mounted src is what runs).
COPY src ./src
RUN uv sync --locked --no-dev

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "src"]

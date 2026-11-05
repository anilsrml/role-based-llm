FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv

RUN useradd --create-home app
WORKDIR /app
RUN chown app /app
USER app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PATH="/app/.venv/bin:$PATH"

# Dependencies first, so code changes do not reinstall them.
COPY --chown=app pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --chown=app . .
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"]

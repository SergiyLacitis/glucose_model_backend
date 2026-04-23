FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./src/

RUN uv sync --frozen --no-install-project --no-dev

COPY . /app

RUN uv sync --frozen --no-dev

CMD ["uv", "run", "app/main.py"]

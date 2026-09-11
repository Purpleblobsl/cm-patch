FROM python:3.14-slim
COPY --from=docker.io/astral/uv:latest /uv /uvx /bin/

# Don't create .pyc files and flush stdout/stderr immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies into /app/.venv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY src ./src
COPY main.py ./

CMD ["uv", "run", "main.py"]

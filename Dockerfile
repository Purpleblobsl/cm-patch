FROM python:3.14-slim
COPY --from=docker.io/astral/uv:latest /uv /uvx /bin/

# Don't create .pyc files and flush stdout/stderr immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into /app/.venv
RUN uv sync --locked --no-install-project

# Copy application
COPY src ./src
COPY main.py ./

CMD ["uv", "run", "main.py"]

FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir \
    "python-telegram-bot[webhooks]>=21.0" \
    "fastapi>=0.110" \
    "uvicorn[standard]>=0.27" \
    "sqlalchemy>=2.0" \
    "alembic>=1.13" \
    "asyncpg>=0.29" \
    "redis>=5.0" \
    "openai>=1.30" \
    "pydantic-settings>=2.2" \
    "structlog>=24.1" \
    "httpx>=0.27" \
    "pyjwt>=2.8"

COPY . .

# Render cung cấp DATABASE_URL dạng postgresql://, cần đổi thành postgresql+asyncpg://
CMD export DATABASE_URL=$(echo $DATABASE_URL | sed 's|^postgres://|postgresql+asyncpg://|;s|^postgresql://|postgresql+asyncpg://|') \
    && alembic upgrade head \
    && uvicorn automod.main:app --host 0.0.0.0 --port ${PORT:-8000}

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
# Сначала только манифесты: зависимости ставятся строго по uv.lock, и этот слой
# переживает правки кода — пересборка на сервере с 1 ГБ RAM занимает секунды.
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/
RUN uv export --frozen --no-dev --no-emit-workspace --package crm-backend -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt
COPY backend/src backend/src
COPY backend/migrations migrations
RUN uv pip install --system --no-cache --no-deps ./backend

ENV MIGRATIONS_DIR=/app/migrations
EXPOSE 8000
CMD ["uvicorn", "crm.main:app", "--host", "0.0.0.0", "--port", "8000"]

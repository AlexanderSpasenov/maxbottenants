FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt -o /usr/local/share/ca-certificates/russian_trusted_root_ca.crt \
    && curl -fsSL https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt -o /usr/local/share/ca-certificates/russian_trusted_sub_ca.crt \
    && update-ca-certificates

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini ./

RUN pip install --upgrade pip && pip install -e .[dev]

COPY tests ./tests
COPY scripts ./scripts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

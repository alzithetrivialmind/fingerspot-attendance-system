FROM python:3.12-slim

WORKDIR /app

# pg_dump/pg_restore versi 16 (sama dengan server PostgreSQL di docker-compose.yml) untuk menu Backup & restore.
# Repo Debian bawaan tidak selalu punya versi 16, jadi pakai repo resmi PostgreSQL (PGDG).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Satu proses saja: feed monitor dan antrean sinkron disimpan di memori proses
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

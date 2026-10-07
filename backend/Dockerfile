# Серверная часть «Обозревателя технической документации».
# Контекст сборки — корень репозитория: docker build -f backend/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY sample-docs /sample-docs

RUN mkdir -p /app/data /app/logs
VOLUME ["/app/data", "/app/logs"]
EXPOSE 8000

# Сигналы останова доходят до uvicorn напрямую (exec-форма), без оболочки-посредника.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

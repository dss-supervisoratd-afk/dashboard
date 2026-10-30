FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd -r -u 10001 amn && mkdir -p /data/uploads && chown amn /data/uploads
USER amn
ENV UPLOAD_DIR=/data/uploads
EXPOSE 8000
# --proxy-headers: o nginx informa host/esquema reais (necessário para o redirect do OAuth)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]

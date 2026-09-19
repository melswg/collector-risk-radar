FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY config config
COPY ml_service_template ml_service_template
RUN useradd -m service && mkdir -p data && chown -R service:service /app
USER service
CMD ["uvicorn", "ml_service_template.app:app", "--host", "0.0.0.0", "--port", "8100"]

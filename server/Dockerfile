FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy source into /app/incident_env/ so `import incident_env` resolves
COPY . ./incident_env/
RUN pip install --no-cache-dir -e ./incident_env/

# Environment defaults
ENV DEPLOYMENT_MODE=single
ENV INCIDENT_ENV_DB_DIR=/tmp/incident_env_dbs
ENV ENABLE_WEB_INTERFACE=true
ENV PORT=8000

EXPOSE 8000

CMD ["uvicorn", "incident_env.server.app:app", "--host", "0.0.0.0", "--port", "8000"]

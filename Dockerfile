# Stage 1: Build React frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python app
FROM python:3.12-slim
WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY wismap.py ./
COPY wismap/ ./wismap/
# Copy built frontend
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 5000

# Worker count is env-tunable via WEB_CONCURRENCY (gunicorn reads it natively when
# --workers is omitted). Default 5; override per environment (security 012 / constitution §Stack).
ENV WEB_CONCURRENCY=5

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wismap.api:app"]

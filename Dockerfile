FROM node:22-slim AS dashboard
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install -e . && pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install 'stable-baselines3>=2.7,<3.0'
COPY --from=dashboard /frontend/dist ./frontend/dist
COPY proofs/ ./proofs/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

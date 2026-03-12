# Use Python 3.10 so we avoid 3.8-only pins (grpcio/aiohttp etc.)
FROM python:3.10-slim

WORKDIR /app

# Install deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code and default config (channels are loaded from DB; this provides message_limit, output_mode, ai_instructions)
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY config.json ./config.json

# Create dirs the app expects at runtime
RUN mkdir -p media

EXPOSE 8000

# Run from /app so ./teledigest.db and ./media and load_dotenv() resolve
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
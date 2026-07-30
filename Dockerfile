FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Streamlit cloud-like
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_SERVER_WEBSOCKET_PING_INTERVAL=15 \
    STREAMLIT_SERVER_MAX_MESSAGE_SIZE=500 \
    STREAMLIT_SERVER_MAX_UPLOAD_SIZE=400 \
    STREAMLIT_SERVER_DISCONNECTED_SESSION_TTL=3600 \
    STREAMLIT_SERVER_ENABLE_WEBSOCKET_COMPRESSION=false

EXPOSE 8501
CMD ["streamlit", "run", "pricebook_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.websocketPingInterval=15", \
     "--server.fileWatcherType=none"]

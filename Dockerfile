FROM python:3.11-slim
# Mineflayer Node.js-e chole, tai node/npm lagbe
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY index.py .
EXPOSE 3000
CMD ["python", "-u", "index.py"]

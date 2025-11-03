# Minimal Dockerfile for the Python service in this repo
# Build a small production image. Adjust python version as needed.
FROM python:3.11

# Create app user
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# Install system deps if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY run ./run
COPY README.md ./

# Expose port if app uses one (adjust as necessary)
EXPOSE 8000

USER appuser

# Default command — change to your app entrypoint as required
CMD ["./run", "test"]

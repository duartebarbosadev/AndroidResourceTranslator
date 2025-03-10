FROM python:3-slim AS builder

# Add only the files specified in .dockerignore
ADD . /app

# Set the working directory inside the container
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the entrypoint
ENTRYPOINT ["python", "/app/AndroidResourceTranslator.py"]

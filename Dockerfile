FROM python:3-slim AS builder
ADD . /app

# Set the working directory inside the container
WORKDIR /app

# Copy the necessary files
COPY AndroidResourceTranslator.py /app/
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the entrypoint
ENTRYPOINT ["python", "/app/AndroidResourceTranslator.py"]

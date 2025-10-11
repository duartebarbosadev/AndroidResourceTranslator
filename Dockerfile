FROM python:3-slim AS builder

# Add only the files specified in .dockerignore
ADD . /workspace

# Set the working directory inside the container
WORKDIR /workspace

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set Python path to ensure imports work correctly
ENV PYTHONPATH=/workspace/app

# Set the entrypoint - points to the script in the app subfolder
ENTRYPOINT ["python", "/workspace/app/AndroidResourceTranslator.py"]

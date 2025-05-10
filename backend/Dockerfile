# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed for some Python packages
# (e.g., for cryptography if it were a dependency, though not strictly needed here)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc libffi-dev musl-dev && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
COPY . .

# Make port 8000 available to other services on the Docker network (and optionally to host)
EXPOSE 8000

# Run main.py when the container launches using Uvicorn
# The host 0.0.0.0 makes it accessible from other Docker containers
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"] 
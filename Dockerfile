# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install GUI dependencies, graphviz, and dos2unix
# Using Debian package manager (apt) available in python:*-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    tk \
    graphviz \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Copy project definition and source code
COPY pyproject.toml README.md /app/
COPY src/ /app/src/

# Convert pyproject.toml line endings to Unix style just in case
RUN dos2unix pyproject.toml || true # Continue if dos2unix isn't needed/fails

# Install the project and its dependencies defined in pyproject.toml
# The '.' tells pip to look for pyproject.toml in the current directory
RUN pip install --no-cache-dir .

# Create a debug wrapper script
RUN echo '#!/bin/bash\n\
echo "=== Starting depviz with debug logging ==="\n\
echo "DISPLAY=$DISPLAY"\n\
echo "Mount contents of /mnt/d:"\n\
ls -la /mnt/d 2>&1 | head -n 10\n\
echo "=== Running depviz ==="\n\
depviz "$@" 2>&1\n\
EXIT_CODE=$?\n\
echo "=== depviz exited with code $EXIT_CODE ==="\n\
' > /app/debug_wrapper.sh && \
chmod +x /app/debug_wrapper.sh

# Define environment variable (can be overridden at runtime)
# Setting DISPLAY here might not always work, often set with `docker run -e`
ENV DISPLAY=:0

# Run the debug wrapper script instead of directly running depviz
ENTRYPOINT ["/app/debug_wrapper.sh"] 
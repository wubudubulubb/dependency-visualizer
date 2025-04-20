# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install GUI dependencies and graphviz (needed for pygraphviz if installed)
# Using Debian package manager (apt) available in python:*-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    tk \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
# Assuming pyproject.toml lists dependencies, copy it and install from it
COPY pyproject.toml README.md /app/

# Install any needed packages specified in pyproject.toml
# Using --no-cache-dir to ensure fresh downloads
# If installing with [viz] extra is desired by default in Docker:
# RUN pip install --no-cache-dir .[viz]
RUN pip install --no-cache-dir .

# Copy the rest of the application code into the container at /app
COPY src/ /app/src/

# Make port 80 available to the world outside this container (if needed, unlikely for this GUI app)
# EXPOSE 80 

# Define environment variables if needed (e.g., for display)
# This might need adjustment depending on the host OS and X server setup
ENV DISPLAY=$DISPLAY

# Run the application using the script defined in pyproject.toml
# Ensure the user running docker has appropriate X server permissions (e.g., xhost +local:docker)
ENTRYPOINT ["depviz"] 
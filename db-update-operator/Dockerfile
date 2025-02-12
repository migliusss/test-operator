# The Operator must be packaged as a Docker image with Python 3.8 or newer.
# Build and push it to Docker Hub.

FROM python:3.12.9-alpine3.21
# Install the required Python packages.
RUN pip install kopf kubernetes
# Set the working directory.
WORKDIR /src
# Copy the operator code into the container.
COPY .. /src
# Use the JSON (exec) form of CMD to ensure proper handling of OS signals.
CMD ["kopf", "run", "databaseUpdate.py", "--verbose"]
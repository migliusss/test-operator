# Use the Node.js base image.
FROM node:latest
# Set the working directory inside the container.
WORKDIR /app
# Copy application files into the container
COPY . .
# Expose the port your app runs on.
EXPOSE 3000
# Command to run the application.
CMD ["node", "index.js"]

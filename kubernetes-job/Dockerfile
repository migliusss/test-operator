FROM python:3.12.9-alpine3.21
WORKDIR /app
COPY job-script.py .
RUN pip install os logging time
CMD ["python", "job-script.py"]
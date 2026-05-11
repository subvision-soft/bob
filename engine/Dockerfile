# Use a compatible base image
FROM python:3.12-slim

# Set the working directory
WORKDIR /

# Copy the requirements file
COPY ./requirements.txt /requirements.txt

# Install system dependencies and PyTorch
RUN apt-get update && apt-get install -y libgl1 libglib2.0-0 \
    && pip install --no-cache-dir -r /requirements.txt

# Copy the rest of the application
COPY ./ /

EXPOSE 9000

# Set the command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]

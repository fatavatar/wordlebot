FROM python:3.8-slim-buster

WORKDIR /app
COPY requirements.txt requirements.txt
CMD pip3 install -r requirements.txt

COPY . .
CMD ["python3", "incomming.py"]

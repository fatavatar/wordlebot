FROM python:3.10

ENV TWILIO_AUTH_TOKEN=token
ENV TWILIO_ACCOUNT_SID=sid
ENV TWILIO_FROM_NUMBER=number
ENV ONESIGNAL_APPID=appid
ENV ONESIGNAL_KEY=secret
ENV PRODUCTION=0
VOLUME /app/data

WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY *.py .
COPY templates templates
COPY static static
CMD ["python3", "-u", "incomming.py"]

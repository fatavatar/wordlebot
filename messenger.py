import logging
import os
from queue import Queue
from threading import Thread
from twilio.rest import Client 
import atexit

logger = logging.getLogger("WordleBot")

account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
from_number = os.environ['TWILIO_FROM_NUMBER']
real_send = False
try:
    real_send_env = os.environ['PRODUCTION']
    if real_send_env == "1":
        real_send = True
except Exception as e:
    real_send = False
logger.debug("Production = " + str(real_send))


q = Queue()
t1 = None

def sendMessage(number, message):
    if t1 is None:
        startMessageQueue()
    q.put((number,message,))
    

def startMessageQueue():
    global t1
    t1 = Thread(target=updateThread)
    t1.start()


def updateThread():
    client = Client(account_sid, auth_token)

    while True:
        number,message = q.get()
        logger.debug("Got Queue item")
        if len(number) == 0:
            break
        if real_send:
            logger.debug("Sending real message")
            client.messages.create(
                            body=message,
                            from_=from_number,
                            to=number
                        )
        else:
            logger.debug("To: " + number + " - " + message)
        

def shutdown():
    print("Shutting down messenger thread")
    global t1
    if t1 is not None:
        q.put(("","",))
        
        t1.join()
        t1 = None



atexit.register(shutdown)
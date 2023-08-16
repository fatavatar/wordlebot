import logging
from queue import Queue
from threading import Thread
from time import sleep
import onesignal
from onesignal.api import default_api
import atexit
from onesignal.model.notification import Notification
from onesignal.model.string_map import StringMap
from onesignal.model.create_notification_success_response import CreateNotificationSuccessResponse
import settings

logger = logging.getLogger("WordleBot")

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
    configuration = onesignal.Configuration(
        app_key = auth_token
    )
    with onesignal.ApiClient(configuration) as api_client:
        # Create an instance of the API class
        api_instance = default_api.DefaultApi(api_client)

        while True:
            number,message = q.get()
            logger.debug("Got Queue item")
            if len(number) == 0:
                break
            logger.debug("Sending Notification to " + number)
            notification = Notification(content=message)
            try:
                # Create notification
                api_response = api_instance.create_notification(notification)
                print(api_response)
            except onesignal.ApiException as e:
                print("Exception when calling DefaultApi->create_notification: %s\n" % e)
                
            

def shutdown():
    print("Shutting down messenger thread")
    global t1
    if t1 is not None:
        q.put(("","",))
        
        t1.join()
        t1 = None



atexit.register(shutdown)

def main():
    configuration = onesignal.Configuration(
        app_key = settings.AUTH_TOKEN
    )
    with onesignal.ApiClient(configuration) as api_client:
        # Create an instance of the API class
        api_instance = default_api.DefaultApi(api_client)
        number="Andrew"
        message="Wes has entered a score!"
        content = StringMap()
        content.set_attribute('en',message)
        logger.debug("Sending Notification to " + number)
        notification = Notification(contents=content, app_id=settings.APP_ID, include_external_user_ids= ["Andrew"], url="https://wordle.thelucks.org/score")
        try:
            # Create notification
            api_response = api_instance.create_notification(notification)
            print(api_response)
        except onesignal.ApiException as e:
            print("Exception when calling DefaultApi->create_notification: %s\n" % e)

if __name__ == "__main__":
    main()
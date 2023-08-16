from dotenv import load_dotenv
import os

load_dotenv()
APP_ID = os.environ['ONESIGNAL_APPID']
AUTH_TOKEN = os.environ['ONESIGNAL_KEY']
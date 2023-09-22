import io
import os
import sys
from flask import Flask, request, redirect, render_template, send_file, url_for
from twilio.twiml.messaging_response import MessagingResponse
import json
import wordle_parser
import logging
from tournament import Tournament, User
import datetime



usercookie="username"
app = Flask(__name__)
app.config.from_pyfile('settings.py')

# def env_override(value, key):
#   return os.getenv(key, value)
# app.jinja_env.filters['env_override'] = env_override



@app.route("/", methods=['GET','POST'])
def index():
    if request.cookies.get(usercookie) is None:
        return render_template('login.html')
    else:
        return render_template('home.html', user=request.cookies.get(usercookie))
        

@app.route("/entries/", methods=['GET','POST'])
def entries():
    
    tournament = Tournament.getCurrentTournament()
    entries = filter(lambda entry: entry.processed == True, tournament.entries)

    return render_template('entries.html', entries=entries)

@app.route("/webshare", methods=['GET', 'POST'])
def webshare():
    username = None
    if request.cookies.get(usercookie) is None:
        if request.args.get('user') is None:
            return "Sorry, you are not logged in"
        else:
            username = request.args.get('user')
    else:
        username = request.cookies.get(usercookie)
    score = request.args.get('score')

    user = User.getUserByName(username)    
    return render_template('webshare.html', score=score, user=user)


@app.route("/share", methods=['GET', 'POST'])
def share():
    username = None
    if request.cookies.get(usercookie) is None:
        if request.args.get('user') is None:
            return "Sorry, you are not logged in"
        else:
            username = request.args.get('user')
    else:
        username = request.cookies.get(usercookie)

    user = User.getUserByName(username)
    if user is None:
        return "Sorry I don't recognize that user"
    
    tournament = Tournament.getCurrentTournament()
    if tournament is None:
        return "Sorry, there is no active tournament currently"

    score = request.args.get('score')
    comment = request.args.get('comment')
    
    logger.info("Entry from user: " + user.name)
    logger.info("Score = " + score)
    logger.info("Comment = " + comment)
    results = wordle_parser.parse(user, score, comment=comment)
    
    if results is None:
        return "Sorry, your score could not be parsed"        

    logger.info("Entry was: " + str(results.guess_count))
    
    if not tournament.validateEntry(results):
        return "Wordle number was not valid for this tournament"        
    
    success = tournament.addScore(results)
    if not success:
        return "Unable to store your score, try again later"        

    # Add a message
    message = ""
    if results.failure:
        message = "A miss? You're stupit."
    elif results.guess_count == 1:
        message = "Fuckin cheater!"
    elif results.guess_count == 2:
        message = "2? You lucky summbitch."
    elif results.guess_count == 3:
        message = "Good job on your 3."
    elif results.guess_count == 4:
        message = "4 - Decidedly below average."
    elif results.guess_count == 5:
        message = "Oooooohh, the magic 8-ball says outlook not so good for that 5."
    elif results.guess_count == 6:
        message = "Do you just want to give up now?"

    return message


@app.route("/login/<code>", methods=['GET','POST'])
def login(code):
    response = redirect('/')
    expire_date = datetime.datetime.now()
    expire_date = expire_date + datetime.timedelta(days=270)
    response.set_cookie(usercookie, code, expires=expire_date)
    return response

@app.route("/sms", methods=['GET', 'POST'])
def sms_reply():
        
    logger.info("HERE")
    """Respond to incoming calls with a simple text message."""
    # Start our TwiML response
    resp = MessagingResponse()

    tournament = Tournament.getCurrentTournament()
    if tournament is None:
        resp.message("Sorry, there is no active tournament currently")
        return str(resp)

    body = request.values.get('Body', None)
    logger.info(json.dumps(request.values, indent=2))

    user = User.getUserByNumber(request.values.get("From", None))

    if user is None:
        resp.message("Sorry, I don't recognize this number.  Please make sure you are registered")
        return str(resp)

    logger.info("Entry from user: " + user.name)
    results = wordle_parser.parse(user, body)
    
    if results is None:
        resp.message("Sorry, your score could not be parsed")
        return str(resp)

    logger.info("Entry was: " + str(results.guess_count))
    
    if not tournament.validateEntry(results):
        resp.message("Wordle number was not valid for this tournament")
        return str(resp)
    
    success = tournament.addScore(results)
    if not success:
        resp.message("Unable to store your score, try again later")
        return str(resp)

    # Add a message
    message = ""
    if results.failure:
        message = "A miss? You're stupit."
    elif results.guess_count == 1:
        message = "Fuckin cheater!"
    elif results.guess_count == 2:
        message = "2? You lucky summbitch."
    elif results.guess_count == 3:
        message = "Good job on your 3."
    elif results.guess_count == 4:
        message = "4 - Decidedly below average."
    elif results.guess_count == 5:
        message = "Oooooohh, the magic 8-ball says outlook not so good for that 5."
    elif results.guess_count == 6:
        message = "Do you just want to give up now?"

    resp.message(message)

    return str(resp)

@app.route("/score", methods=['GET', 'POST'])
def getscore():
    wordle = request.values.get('wordle', None)
    current = Tournament.getCurrentTournament()
    if current is None:
        return "Sorry no current tournament"
    day = None
    if wordle is None:
        day = current.getLatestDay()
    else:
        day = current.getDay(int(wordle))

    return render_template("score.html", wordle=day)



@app.route("/manifest.json", methods=['GET', 'POST'])
def manifest():
    return send_file(
        "static/manifest.json",
        download_name="manifest.json",
    )
   
@app.route("/sw.js", methods=['GET', 'POST'])
def sw():
    return send_file(
        "static/js/sw.js",
        download_name="sw.js",
    )
   
@app.route("/offline.html", methods=['GET', 'POST'])
def offline():
    return send_file(
        "static/offline.html",
        download_name="offline.html",
    )
    
if __name__ == "__main__":

    logger = logging.getLogger("WordleBot")
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    handler = logging.StreamHandler()
    try:
        prod = os.environ['PRODUCTION']
        if prod == "1":
            prod = True
    except Exception as e:
        prod = False    

    if prod:
        handler = logging.StreamHandler(sys.stdout)
        
    handler.setFormatter(formatter)

    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.debug("Startup")
    app.run(host="0.0.0.0",debug=True)





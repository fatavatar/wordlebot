import os
import sys
from flask import Flask, request, render_template
from twilio.twiml.messaging_response import MessagingResponse
import json
import wordle_parser
import logging
from tournament import Tournament, User

app = Flask(__name__)

@app.route("/test", methods=['GET', 'POST'])
def test():
    logger.info("BOO")
    return "HEYOO"

@app.route("/entries/", methods=['GET','POST'])
def entries():
    tournament = Tournament.getCurrentTournament()
    
    
    
    entries = filter(lambda entry: entry.processed == True, tournament.entries)

    return render_template('entries.html', entries=entries)

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





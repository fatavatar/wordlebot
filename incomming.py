from flask import Flask, request, redirect
from twilio.twiml.messaging_response import MessagingResponse
import json
import wordle_parser
import storage
import os
from queue import Queue
from threading import Thread
from twilio.rest import Client 

account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
from_number = os.environ['TWILIO_FROM_NUMBER']
client = Client(account_sid, auth_token)

app = Flask(__name__)
q = Queue()

@app.route("/test", methods=['GET', 'POST'])
def test():
    print("BOO")
    return "HEYOO"

@app.route("/sms", methods=['GET', 'POST'])
def sms_reply():
        
    print("HERE")
    """Respond to incoming calls with a simple text message."""
    # Start our TwiML response
    resp = MessagingResponse()

    tournament = storage.getCurrentTournament()
    if tournament is None:
        resp.message("Sorry, there is no active tournament currently")
        return str(resp)

    print(json.dumps(tournament, indent=2))

    body = request.values.get('Body', None)
    print(json.dumps(request.values, indent=2))


    user = storage.getUserByNumber(request.values.get("From", None))
    print(json.dumps(user, indent=2))
    if user is None:
        resp.message("Sorry, I don't recognize this number.  Please make sure you are registered")
        return str(resp)

    results = wordle_parser.parse(body)
    
    if results is None:
        resp.message("Sorry, your score could not be parsed")
        return str(resp)

    
    print(json.dumps(results, indent=2))
    if not validateEntry(tournament, results):
        resp.message("Wordle number was not valid for this tournament")
        return str(resp)
    
    success = storage.enterScore(user['id'], results['wordle'], results['guess_count'], 
        results['failure'],  results['guesses'], results['flavor_text'])
    if not success:
        resp.message("Unable to store your score, try again later")
        return str(resp)

    # Add a message
    resp.message("Thanks!  Great work on your " + str(results["guess_count"]))

    q.put(results['wordle'])

    return str(resp)

def sendDailyTotals(info):
    print("Sending total")
    users = storage.getUsers()
    for user in users:
        for result in info['users']:
            
            guess = "X/6*"
            if result['failure'] == 0:
                guess = str(result['guess_count']) + "/6*"
            body = result['name'] + ":\n" + \
                "Wordle " + str(info['wordle']) + " " + guess + "\n\n" + \
                result['guesses'] + "\n" + result['flavor_text']

            client.messages \
                    .create(
                        body=body,
                        from_=from_number,
                        to=user['phone']
                    )
    for user in users:
        body="Results for day " + str(info['day']) + ":\n"
        place = 1
        for totalList in info['totals']:
            print(totalList)
            for total in totalList:
                body = body + str(place) + ") " + total['name'] + \
                    " - Xs: " + str(total['misses']) + " " + "Total: " + \
                    str(total['guess_count']) + "\n"
                
            place = place +len(totalList)
        body=body[:-1]

        client.messages \
                    .create(
                        body=body,
                        from_=from_number,
                        to=user['phone']
                    )



def validateEntry(tournament, results):
    day = results['wordle'] - tournament['start_wordle']
    if day >= 0 and day < tournament['days']:
        return True

def updateThread():
    while True:
        wordle = q.get()

        days = storage.reconcile(wordle)

        for day in days:
            info = storage.getResultsForDay(day)
            if info is not None:
                sendDailyTotals(info)

def startTournament(wordle, days):
    tournament = storage.getCurrentTournament()
    if tournament is None:
        users = storage.getUsers()
        storage.startTournament(wordle, days)
        print(str(len(users)))
        for user in users:
            client.messages \
                .create(
                    body=user['name'] + ", you've been registered for a " + str(days) + " day wordle tournament starting with wordle " + str(wordle) + ".  Please text your daily scores to this number.  Good luck!",
                    from_=from_number,
                    to=user['phone']
                )


if __name__ == "__main__":
    storage.setup()
    t1 = Thread(target=updateThread)
    t1.start()

    app.run(host="0.0.0.0",debug=True)

import sqlite3
import os
import traceback
from contextlib import closing

db_name = "data/wordle.db"
def setup():    
    if os.path.isfile(db_name):
        return

    with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:

        cur.execute("""CREATE TABLE user(
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                name TEXT NOT NULL, 
                phone TEXT NOT NULL
            );""")
        cur.execute("""CREATE TABLE tournament (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                start_wordle INTEGER NOT NULL, 
                days INTEGER NOT NULL, 
                current INTEGER DEFAULT FALSE NOT NULL
            );""")

        cur.execute(""" CREATE TABLE entry (
                tournament_id INTEGER NOT NULL, 
                user_id INTEGER NOT NULL, 
                wordle INTEGER NOT NULL, 
                guess_count INTEGER, 
                failure INTEGER, 
                guesses TEXT NOT NULL, 
                flavor_text TEXT,
                processed INTEGER DEFAULT FALSE NOT NULL,
                PRIMARY KEY (user_id, wordle),
                FOREIGN KEY (tournament_id) REFERENCES tournament (id) 
                    ON DELETE CASCADE ON UPDATE NO ACTION,
                FOREIGN KEY (user_id) REFERENCES user (id) 
                    ON DELETE CASCADE ON UPDATE NO ACTION 
            ); """)

       
        con.commit()

def startTournament(wordle, length):
    with closing(sqlite3.connect(db_name)) as con, con,  \
        closing(con.cursor()) as cur:
        cur.execute("INSERT INTO tournament (start_wordle, days, current) VALUES (?, ?, TRUE)", (wordle,length))
        con.commit()

def getUsers():
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            cur.execute("SELECT id, name, phone FROM user")
            users = []
            for row in cur:
                user = {}
                user['id'] = row[0]
                user['name'] = row[1]
                user['phone'] = row[2]
                users.append(user)
            return users
    except Exception as e:
        print("Error getting users: " + str(e))
        return None

def getUserByNumber(phone_number):
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            cur.execute("SELECT id, name, phone FROM user WHERE phone = ?", (phone_number,))
            user_id, name, phone = cur.fetchone()
            user = {}
            user['id'] = user_id
            user['name'] = name
            user['phone'] = phone
            return user
    except Exception as e:
        return None

def enterScore(userid, wordle, guesscount, failure, guesses, flavor_text):
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            if failure:
                guesscount=None
            tournament = getCurrentTournament()
            cur.execute("""INSERT INTO entry (tournament_id, user_id, wordle, guess_count, 
                    failure, guesses, flavor_text) VALUES (?,?,?,?,?,?,?);
                """, 
                (tournament['id'], userid, wordle, guesscount, failure, guesses, flavor_text))
            con.commit()
            return True
    except Exception as e:
        print("Error entering score: " + str(e))
        return False

def getCurrentTournament():
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            cur.execute("SELECT id, start_wordle, days FROM tournament WHERE current = TRUE")
            
            tournament_id, start_wordle, days = cur.fetchone()
            tournament={}
            tournament['id']=tournament_id
            tournament['start_wordle']=start_wordle
            tournament['days']=days
            return tournament
    except Exception as e:
        print("Error getting tournament: " + str(e))
        return None

def reconcile(wordle):
    days = closePreviousDays(wordle)
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            
            cur.execute("""SELECT id FROM user WHERE id NOT IN (SELECT user_id FROM entry 
                WHERE entry.wordle = ?)""", (wordle,))
            count = len(cur.fetchall())
            if count > 0:
                print("Still awaiting " + str(count) + " results")            
            else:
                closeDay(wordle)
                days.append(wordle)
    except Exception as e: 
        print("Error checking day done: " + str(e))
    
    return days

def closePreviousDays(wordle):
    days = []
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            tournament = getCurrentTournament()
            cur.execute("""SELECT DISTINCT(wordle) FROM entry WHERE tournament_id = ? AND wordle < ? AND processed = FALSE ORDER BY wordle ASC""", (tournament['id'], wordle))

            for row in cur:
                if closeDay(row[0]):
                    days.append(row[0])

    except Exception as e:
        print("Exception closing previous days: " + str(e))
    
    return days

#def insertAttempt(user_id, wordle, guess_count, failure, guesses, flavor_text):

def closeDay(wordle):
    users = []
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            
            cur.execute("""SELECT id FROM user WHERE id NOT IN (SELECT user_id FROM entry 
                WHERE entry.wordle = ?)""", (wordle,))
            for row in cur:
                users.append(row[0])

    except Exception as e:
        print("Error finding users to close day " + str(wordle) + ": " + str(e))
        return False


    for user in users:
        enterScore(user, wordle, None, True, "No Guesses Entered", None)
        
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            
            cur.execute("""UPDATE entry SET processed = TRUE WHERE wordle = ?""", (wordle,))
            con.commit()
            return True
    except Exception as e:
        print("Error closing wordle " + str(wordle) + ": " + str(e))
        return False


def getResultsForDay(wordle):
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:

            tournament = getCurrentTournament()
            day = wordle - tournament['start_wordle'] + 1

            cur.execute("""SELECT name, guess_count, guesses, flavor_text, failure FROM 
                entry INNER JOIN user on entry.user_id = user.id WHERE entry.wordle = ?""", (wordle,))

            users = []
            for row in cur:
                user = {}
                user['name'] = row[0]
                user['guess_count'] = row[1]
                user['guesses'] = row[2]
                user['flavor_text'] = row[3]
                user['failure'] = row[4]
                users.append(user)

            totals = {}
            cur.execute("""SELECT name, guess_count, failure FROM entry INNER JOIN user 
                ON entry.user_id = user.id WHERE tournament_id = ?""", (tournament['id'], ))
            for row in cur:
                if row[0] not in totals:
                    total = {}
                    total['name'] = row[0]
                    total['guess_count'] = 0
                    total['misses'] = 0
                    totals[row[0]] = total
                total = totals[row[0]]
                if row[2] == 1:
                    total['misses'] = total['misses'] + 1
                else:
                    total['guess_count'] = total['guess_count'] + row[1]
                totals[row[0]] = total

            totalList = []
            for total in totals.values():
                if len(totalList) == 0:
                    innerList = []
                    innerList.append(total)
                    totalList.append(innerList)
                else:
                    index=0
                    for list in totalList:
                        oldTotal = list[0]
                        if oldTotal['misses'] == total['misses'] and oldTotal['guess_count'] == total['guess_count']:
                            list.append(total)
                            break
                        elif oldTotal['misses'] > total['misses']:                        
                            innerList = []
                            innerList.append(total)
                            totalList.insert(index, innerList)
                            break
                        elif oldTotal['misses'] == total['misses'] and oldTotal['guess_count'] > total['guess_count']:                        
                            innerList = []
                            innerList.append(total)
                            totalList.insert(index, innerList)
                            break                
                        else:                    
                            index = index + 1
                    if len(totalList) == index:
                        innerList = []
                        innerList.append(total)
                        totalList.append(innerList)

            results = {}
            results['day'] = day
            results['wordle'] = wordle
            results['users'] = users
            results['totals'] = totalList
            return results        

    except Exception as e:
        print("Error getting results for day " + str(wordle) + ": " + str(e))
        traceback.print_exc()
        return None

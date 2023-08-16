import sqlite3
import os
import logging
from contextlib import closing

class StorageUser:
    def __init__(self, id, name, number):
        self.name = name
        self.number = number
        self.id = id

class StorageEntry:
    def __init__(self, user, wordle, guess_count, failure, guesses, flavor_text, processed):
        self.user = user
        self.wordle = wordle
        self.guess_count = guess_count
        self.failure = failure
        self.guesses = guesses
        self.flavor_text = flavor_text
        self.processed = processed

class StorageTournament:
    def __init__ (self, id, start_wordle, days, current):
        self.id = id
        self.start_wordle = start_wordle
        self.days = days
        self.current = current

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

def stopTournament():
    tournament = getCurrentTournament()
    if tournament is None:
        logger.debug("Error - there is no current tournament")
        return False

    with closing(sqlite3.connect(db_name)) as con, con,  \
        closing(con.cursor()) as cur:
        cur.execute("UPDATE tournament SET current = FALSE WHERE current = TRUE")
        con.commit()
    return True
        

def startTournament(wordle, length):
    if getCurrentTournament() is not None:
        logger.debug("Error - there is already a tournament running")
        return False
    with closing(sqlite3.connect(db_name)) as con, con,  \
        closing(con.cursor()) as cur:
        cur.execute("INSERT INTO tournament (start_wordle, days, current) VALUES (?, ?, TRUE)", (wordle,length))
        con.commit()
    return True

def getUsers():
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            cur.execute("SELECT id, name, phone FROM user")
            users = []
            for row in cur:
                user = StorageUser(row[0], row[1], row[2])                
                users.append(user)
            return users
    except Exception as e:
        logger.debug("Error getting users: " + str(e))
        return None

def addUser(name, phone_number):
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            cur.execute("INSERT INTO user (name, phone) VALUES (?,?) ", (name, phone_number,))
            
        return True
    except Exception as e:
        logger.debug("Error adding user: ", str(e))
        return False


def getUserByName(username):
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            cur.execute("SELECT id, name, phone FROM user WHERE name = ?", (username,))
            user_id, name, phone = cur.fetchone()
            user = StorageUser(user_id, name, phone)
            return user
    except Exception as e:
        return None

def getUserByNumber(phone_number):
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            cur.execute("SELECT id, name, phone FROM user WHERE phone = ?", (phone_number,))
            user_id, name, phone = cur.fetchone()
            user = StorageUser(user_id, name, phone)
            return user
    except Exception as e:
        return None

def enterScore(tournament_id, userid, wordle, guesscount, failure, guesses, flavor_text):
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            if failure:
                guesscount=None
            cur.execute("""INSERT INTO entry (tournament_id, user_id, wordle, guess_count, 
                    failure, guesses, flavor_text) VALUES (?,?,?,?,?,?,?);
                """, 
                (tournament_id, userid, wordle, guesscount, failure, guesses, flavor_text))
            con.commit()
            return True
    except Exception as e:
        logger.debug("Error entering score: " + str(e))
        return False

def getCurrentTournament():
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            cur.execute("SELECT id, start_wordle, days FROM tournament WHERE current = TRUE")
            
            tournament_id, start_wordle, days = cur.fetchone()
            return StorageTournament(tournament_id, start_wordle, days, True)
            
    except Exception as e:
        logger.debug("Error getting tournament: " + str(e))
        return None

def getEntries(tournament_id):
    try:
        users = getUsers()
        usermap = {}
        entries = []
        for user in users:
            usermap[user.id] = user
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            cur.execute("""SELECT user_id, wordle, guess_count, 
                failure, guesses, flavor_text, processed FROM entry WHERE 
                tournament_id = ? ORDER BY wordle ASC, user_id ASC""", (tournament_id,))
            for row in cur:
                entry = StorageEntry(usermap[row[0]], row[1], row[2], row[3], row[4], row[5], row[6])
                entries.append(entry)
        return entries
    except Exception as e:
        logger.debug("Error getting entries for tournament " + str(tournament_id) + ": " + str(e))
        return None
    

def setProcessed(wordle):      
    try:
        with closing(sqlite3.connect(db_name)) as con, con,  \
            closing(con.cursor()) as cur:
            
            cur.execute("""UPDATE entry SET processed = TRUE WHERE wordle = ?""", (wordle,))
            con.commit()
            return True
    except Exception as e:
        logger.debug("Error closing wordle " + str(wordle) + ": " + str(e))
        return False

setup()
logger = logging.getLogger("WordleBot")
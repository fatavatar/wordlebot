import logging
import os
import time
import storage
import sys
import notifier

class User:
    @staticmethod
    def __fromStorage(storage_user):
        return User(storage_user.id, storage_user.name, storage_user.number)


    def fromStorage(storage_user):
        return User.__fromStorage(storage_user)

    @staticmethod
    def getUserByNumber(number):
        return User.__fromStorage(storage.getUserByNumber(number))
    
    @staticmethod
    def getUserByName(name):
        return User.__fromStorage(storage.getUserByName(name))

    @staticmethod
    def getUsers():
        storage_list = storage.getUsers()
        users = []
        for user in storage_list:
            users.append(User.__fromStorage(user))
        return users

    def __init__(self, id, name, number):
        self.name = name
        self.number = number
        self.id = id

class Entry:

    @staticmethod
    def __fromStorage(storage_entry):
        user = User.fromStorage(storage_entry.user)
        return Entry(user,
            storage_entry.wordle,
            storage_entry.guess_count,
            storage_entry.failure,
            storage_entry.guesses,
            storage_entry.flavor_text,
            storage_entry.processed)

    @staticmethod
    def getEntries(tournament_id):
        storage_list = storage.getEntries(tournament_id)
        entries = []
        for entry in storage_list:
            entries.append(Entry.__fromStorage(entry))
        return entries

    def __init__(self, user, wordle, guess_count, failure, guesses, flavor_text, processed=False):
        self.user = user
        self.wordle = wordle
        self.guess_count = guess_count
        self.failure = failure
        self.guesses = guesses
        self.flavor_text = flavor_text
        self.processed = processed
    
    def __str__(self):
        return "Entry: " + self.user + " - Wordle: " + self.wordle + " " + str(self.guess_count)

class UserStanding:
    def __init__(self, user):
        self.user = user
        self.misses = 0
        self.guesses = 0
        self.place = 0
    
class Standings:
    def __init__(self, users):
        self.totals = {}
        self.last_wordle = 0
        
        for user in users:
            self.totals[user.id] = UserStanding(user)

    def __processEntry(self, entry):
        total = self.totals[entry.user.id]
        if entry.processed:
            if entry.wordle > self.last_wordle:
                self.last_wordle = entry.wordle

            if entry.failure == 1:
                total.misses = total.misses + 1
            else:
                total.guesses = total.guesses + entry.guess_count

    def processEntries(self, entries, wordle):
        for entry in entries:
            if entry.wordle <= wordle:
                self.__processEntry(entry)
        self.__calculate()        

    def processEntry(self, entry):
        self.__processEntry(entry)
        
        #self.totals[row[0]] = total
        self.__calculate()

    
    def __calculate(self):        
        
        totalList = []
        for total in self.totals.values():
            if len(totalList) == 0:
                innerList = []
                innerList.append(total)
                totalList.append(innerList)
            else:
                index=0
                for list in totalList:
                    oldTotal = list[0]
                    if oldTotal.misses == total.misses and oldTotal.guesses == total.guesses:
                        list.append(total)
                        break
                    elif oldTotal.misses > total.misses:                        
                        innerList = []
                        innerList.append(total)
                        totalList.insert(index, innerList)
                        break
                    elif oldTotal.misses == total.misses and oldTotal.guesses > total.guesses:                        
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
        rank = 1
        for innerlist in totalList:
            for standing in innerlist:
                standing.place = rank
            rank = rank + len(innerlist)

    def getSorted(self):
        sorted = []
        for total in self.totals.values():
            index=0
            added = False
            for item in sorted:
                if total.place <= item.place:
                    sorted.insert(index, total)
                    added = True
                    break
                index = index + 1
            if not added:
                sorted.append(total)
        return sorted
            

class Day:

    def __init__(self, wordle, done, entries, standings, hasnext, hasprev):
        self.id = id
        self.wordle = wordle 
        self.hasprev = hasprev
        self.hasnext = hasnext
        self.done = done
        self.entries = entries
        self.standings = standings

class Tournament:

    @staticmethod
    def __fromStorage(storage_tournament):
        return Tournament(storage_tournament.id,
            storage_tournament.start_wordle,
            storage_tournament.days,
            storage_tournament.current)

    @staticmethod
    def getCurrentTournament():
        storage_tournament = storage.getCurrentTournament()
        if storage_tournament is not None:
            return Tournament.__fromStorage(storage_tournament)
        return None
    
    @staticmethod
    def startTournament(wordle, days):
        tournament = Tournament.getCurrentTournament()
        if tournament is None:
            users = User.getUsers()        
            if users is not None and storage.startTournament(wordle, days):
                for user in users:
                    body = user.name + ", you've been registered for a " + str(days) + " day wordle tournament starting with wordle " + str(wordle) + ".  Please text your daily scores to this number.  Good luck!"
                    notifier.sendMessage(user.name, body)                    

                return True
        return False

    def getStandings(self, wordle = None):
        if wordle is None:
            wordle = self.__getCurrentWordle()

        totals = Standings(self.users)
        totals.processEntries(self.entries, wordle)
        return totals
    
    

    def __getCurrentWordle(self):
        wordle = self.start_wordle
        for entry in self.entries:
            if entry.wordle > wordle:
                wordle = entry.wordle
        return wordle

    def getLatestDay(self):
        wordle = self.__getCurrentWordle()
        return self.getDay(wordle)
    
    def getDay(self, wordle):
        found_users = []
        entries = []
        done = False
        for entry in self.entries:
            if entry.wordle == wordle:
                found_users.append(entry.user.id)
                if entry.processed:
                    done = True
                entries.append(entry)
                        
        for user in self.users:
            if user.id not in found_users:                
                entries.append(Entry(user, wordle, None, False, None, None))
        
        standings = None
        if done:
            standings = self.getStandings(wordle)
        return Day(wordle, done, entries, Results(self, standings), wordle < self.__getCurrentWordle(), wordle > self.start_wordle)
    

        
    def closeDay(self, wordle):
        found_users = []
        for entry in self.entries:
            if entry.wordle == wordle:
                found_users.append(entry.user.id)
        
        for user in self.users:
            if user.id not in found_users:                
                self.__addScore(Entry(user, wordle, None, True, "No Guesses Entered", None))
        
        storage.setProcessed(wordle)
        self.entries = storage.getEntries(self.id)

    def stopTournament(self):
        for wordle in range(self.start_wordle, self.start_wordle + self.days):
            self.closeDay(wordle)
        self.entries = Entry.getEntries(self.id)

        if storage.stopTournament():
            self.entries = Entry.getEntries(self.id)
            self.current = False
            if len(self.users) > 0:
                # Get Standings
                for user in self.users:
                    body = user['name'] + ", The tournament has ended"
                    notifier.sendMessage(user['name'], body)                    

                return True
        return False

    def __init__(self, id, start_wordle, days, current):
        self.id = id
        self.start_wordle = start_wordle
        self.days = days
        self.current = current
        self.users = User.getUsers()
        self.entries = Entry.getEntries(id)        

    def validateEntry(self, entry):
        day = entry.wordle - self.start_wordle
        if day >= 0 and day < self.days:
            return True
        return False

    def __addScore(self, score):
        if not storage.enterScore(self.id, score.user.id, score.wordle, score.guess_count, 
            score.failure, score.guesses, score.flavor_text):
            return False
        return True


    def addScore(self, score):
        if self.validateEntry(score):
            if score.wordle > self.start_wordle:
                # Close previous day just in case
                self.closeDay(score.wordle - 1)

        if not self.__addScore(score):
            return False

        for user in self.users:
            if user.id != score.user.id:
                message = score.user.name + " has entered their score"
                if score.flavor_text is not None and len(score.flavor_text) > 0:
                    message = message + "\nThey said: " + score.flavor_text
                notifier.sendMessage(user.name, message)
        self.entries = Entry.getEntries(self.id)
        todays_entries = []
        for entry in self.entries:
            if entry.wordle == score.wordle:
                todays_entries.append(entry)
        if len(todays_entries) == len(self.users):
            self.closeDay(score.wordle)
            self.reportDay(score.wordle)
            
            # results = Results(self)
            # for user in self.users:
            #     notifier.sendMessage(user.name, str(results))
            
        
        return True
        

    def reportDay(self, wordle):
        for user in self.users:                    
            notifier.sendMessage(user.name, "All entries are completed")
        

class Results:
    def __init__(self, tournament, standings=None):
        if standings is None:
            standings = tournament.getStandings()
        self.standings = standings.getSorted()

        self.day = standings.last_wordle - tournament.start_wordle + 1
        self.final = (self.day == tournament.days)
        self.wordle = standings.last_wordle

        logger.debug("Last = " + str(standings.last_wordle))
        logger.debug("Start = " + str(tournament.start_wordle))
        logger.debug("Days = " + str(tournament.days))
        logger.debug("Results Day = " + str(self.day))

    def __str__(self):
        state = ":"
        if self.final:
            state = " (FINAL):"
        text = "Results for day " + str(self.day) + state
        for standing in self.standings:
            text = text + "\n" + str(standing.place) + ") " + standing.user.name + \
                " - Xs: " + str(standing.misses) + " Total: " + str(standing.guesses) 
        return text

        
    

    
        
def usage():
    logger.debug("Usage: " + sys.argv[0] + " <start/stop> [numberofdays] [start_wordle]")
    logger.debug("   Stop command requires no additional arguments")
    sys.exit(1)





def main():
    if len(sys.argv) < 2:
        usage()

    command=sys.argv[1]
    if command == "stop":
        logger.debug("Stopping tournament")
        if storage.stopTournament():
            logger.debug("Success!")
            
        else:
            logger.debug("Failure!")


    elif len(sys.argv) != 4:
        usage()
    else:
        number=sys.argv[2]
        wordle=sys.argv[3]

        logger.debug("Starting tournament")
        if Tournament.startTournament(wordle, number):  
            time.sleep(10)  
            logger.debug("Success!")

        else:
            logger.debug("Failed!")
    
    notifier.shutdown()

logger = logging.getLogger("WordleBot")

if __name__ == "__main__":
    
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    handler = logging.StreamHandler()
        
    handler.setFormatter(formatter)

    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.debug("Startup")
    main()
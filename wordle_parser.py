import logging
import re
from tournament import Entry


def parse(user, body):
    try:
        # Parse line by line
        lines = body.split("\n")

        logger.debug(len(lines))

        if not lines[0].endswith("*"):
            logger.debug("Whoops, not hard mode!")
            return None

        returnval = {}
        result = re.search(r"Wordle (\b\d+) (\b[\dX]+)/6*", lines[0])
        logger.debug(result.groups())
        wordle=int(result.group(1))
        guesses=result.group(2)
        rows=6
        failure = True
        if guesses != 'X':
            rows=int(guesses)
            failure = False
        for x in range(rows):
            logger.debug(lines[2 + x])
        flavor = ""
        if len(lines) > rows+2:
            flavor='\n'.join(lines[rows+2:])
            if flavor.endswith('\n'):
                flavor = flavor[:-1]
                logger.debug(flavor)
        returnval = Entry(user, wordle, rows, failure, "\n".join(lines[2:rows+2]), flavor)

        return returnval
    except Exception as e:
        logger.debug("Error " + str(e))
        return None

    
logger = logging.getLogger("WordleBot")
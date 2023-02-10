import re


def parse(body):
    try:
        # Parse line by line
        lines = body.split("\n")

        print(len(lines))

        if not lines[0].endswith("*"):
            print("Whoops, not hard mode!")
            return None

        returnval = {}
        result = re.search(r"Wordle (\b\d+) (\b[\dX]+)/6*", lines[0])
        print(result.groups())
        wordle=int(result.group(1))
        guesses=result.group(2)
        rows=6
        failure = True
        if guesses != 'X':
            rows=int(guesses)
            failure = False
        for x in range(rows):
            print(lines[2 + x])
        flavor = ""
        if len(lines) > rows+2:
            flavor='\n'.join(lines[rows+2:])
            if flavor.endswith('\n'):
                flavor = flavor[:-1]
                print(flavor)
        returnval["wordle"] = wordle
        returnval["guess_count"] = rows
        returnval["failure"] = failure
        returnval["guesses"] = "\n".join(lines[2:rows+2])
        returnval["flavor_text"] = flavor

        return returnval
    except Exception as e:
        print("Error " + str(e))
        return None

    

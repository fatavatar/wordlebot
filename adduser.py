import storage
import sys

if len(sys.argv) != 3:
    print("Usage: " + sys.argv[0] + " <name> <phonenumber>")
    print("   Phone number should be in the format +1XXXXXXX")
    sys.exit(1)

name=sys.argv[1]
number=sys.argv[2]
print("Adding user " + name + " with number " + number)
if storage.addUser(name, number):
    print("Success!")
else:
    print("Failed!")



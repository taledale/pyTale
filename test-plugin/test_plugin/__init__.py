import test_plugin.helpers
from test_plugin.utils import math

print("Hello from test_plugin!")
print(f"Version: {test_plugin.helpers.get_version()}")
print(f"Greeting: {test_plugin.helpers.get_greeting('Plugin')}")
print(f"2 + 3 = {math.add(2, 3)}")
print(f"4 * 5 = {math.multiply(4, 5)}")

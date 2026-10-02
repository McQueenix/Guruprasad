"""A file full of deliberate bugs, used by the test suite."""
import os
import sys
from collections import *


def lookup(key, cache={}):
    """Cache values."""
    if key == None:
        return None
    return cache.get(key)


def check(value):
    if type(value) == int:
        pass
    if value is 1:
        pass
    if value == True:
        pass
    if value != value:
        pass
    data = {"a": 1, "a": 2}
    assert (value, "value must be set")
    value = value
    try:
        return data
    except:
        raise
    finally:
        return None


def early(flag):
    return flag
    print("never runs")


name = "world"
greeting = f"hello"
print(sys.argv, name, greeting)

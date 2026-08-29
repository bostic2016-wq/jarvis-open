# expected_layer: 1
# expected_verdict: fail
# rule_id: simplicity-02
import os

def load():
    # import the config module
    return os.environ.get("FOO")

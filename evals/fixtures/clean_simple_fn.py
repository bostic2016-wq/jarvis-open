# expected_layer: 1
# expected_verdict: pass
# rule_id: simplicity-01
def process(items):
    total = 0
    for item in items:
        total += item
    return total

# expected_layer: 2
# expected_verdict: pass
# rule_id: agent-workflow
def format_label(name: str, score: float) -> str:
    return f"{name}: {score:.1f}"

// expected_layer: 1
// expected_verdict: pass
// rule_id: simplicity-02
export function tierScore(player: { adp: number }) {
  // Tier 1 when ADP is inside the window we care about for this horizon
  return player.adp <= 24;
}

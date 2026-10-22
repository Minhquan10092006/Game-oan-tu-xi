"""K71 protocol 1.0: one-based coordinates, one JSON input/output per process.

Minimal legal strategy: prefer an immediate win, capture, then approach the goal.
Read docs/LUAT_THI_DAU_K71.md before submitting your own strategy.
"""
import json
import sys


def choose(state):
    goal = state['players'][state['current_player']]['goal']
    def score(move):
        distance = max(abs(goal[0] - move['to'][0]), abs(goal[1] - move['to'][1]))
        return (move['wins_immediately'], move['capture'], -distance)
    return max(state['legal_moves'], key=score)


def main():
    state = json.load(sys.stdin)
    move = choose(state)
    print(json.dumps({'move': {key: move[key] for key in ('piece_id', 'from', 'to')},
                      'userdata': None}, separators=(',', ':')))


if __name__ == '__main__':
    main()

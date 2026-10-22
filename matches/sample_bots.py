"""Trusted built-in strategies for the public demo; never evaluates uploaded code."""
class SampleBotRunner:
    def __init__(self, source, workdir, timeout):
        self.defensive = source == 'defensive'

    def run_turn(self, state):
        goal = state['players'][state['current_player']]['goal']
        def score(move):
            distance = max(abs(goal[0] - move['to'][0]), abs(goal[1] - move['to'][1]))
            return (move['wins_immediately'], int(move['capture']) * (20 if self.defensive else 8) - distance)
        move = max(state['legal_moves'], key=score)
        return {'move': {key: move[key] for key in ('piece_id', 'from', 'to')}}, {'elapsed_ms': 0, 'stderr': '', 'exit_code': 0}

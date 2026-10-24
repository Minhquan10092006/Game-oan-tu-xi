"""Sample source is sent to the same Docker sandbox as student code."""
HEADER = 'import json,sys\ns=json.load(sys.stdin)\nmoves=s["legal_moves"]\ngoal=s["players"][s["current_player"]]["goal"]\n'
FOOTER = '\nprint(json.dumps({"move":{k:m[k] for k in ("piece_id","from","to")},"userdata":None}))\n'
BOTS = {
    'first': {'name': 'Bot cơ bản', 'description': 'Chọn nước hợp lệ đầu tiên, phù hợp kiểm tra giao thức.',
              'source': HEADER + 'm=moves[0]' + FOOTER},
    'aggressive': {'name': 'Bot tiến công', 'description': 'Ưu tiên thắng ngay, bắt quân và tiến về đích.',
        'source': HEADER + 'm=max(moves,key=lambda x:(x["wins_immediately"],int(x["capture"])*8-max(abs(goal[0]-x["to"][0]),abs(goal[1]-x["to"][1]))))' + FOOTER},
    'defensive': {'name': 'Bot ưu tiên bắt quân', 'description': 'Đặt trọng số bắt quân cao hơn việc tiến về đích.',
        'source': HEADER + 'm=max(moves,key=lambda x:(x["wins_immediately"],int(x["capture"])*20-max(abs(goal[0]-x["to"][0]),abs(goal[1]-x["to"][1]))))' + FOOTER},
}

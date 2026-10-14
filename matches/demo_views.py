"""Small public API for the upload-and-replay demo; deliberately separate from legacy Judge0 APIs."""
from __future__ import annotations
import os, tempfile
from pathlib import Path
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from .game_engine import board_presets
from .match_manager import MatchManager

MATCHES = {}
MAX_UPLOAD = 256 * 1024

@require_GET
def boards(request):
    return JsonResponse({name: {k: v for k, v in value.items() if k != "initial_pieces"} for name, value in board_presets().items()})

@csrf_exempt
@require_POST
def create_demo_match(request):
    p1, p2 = request.FILES.get("player1_file"), request.FILES.get("player2_file")
    if not p1 or not p2:
        return JsonResponse({"error": "Cần tải lên bot Player 1 và Player 2."}, status=400)
    if any(Path(f.name).suffix.lower() != ".py" or f.size > MAX_UPLOAD for f in (p1, p2)):
        return JsonResponse({"error": "Chỉ chấp nhận hai file Python (.py), tối đa 256 KB mỗi file."}, status=400)
    preset = request.POST.get("preset", "classic_9x9")
    try:
        max_plies = min(max(int(request.POST.get("max_plies", 300)), 1), 300)
        timeout = min(max(float(request.POST.get("timeout", 2)), .1), 10)
        with tempfile.TemporaryDirectory(prefix="ott-upload-") as directory:
            paths = []
            for idx, upload in enumerate((p1, p2), 1):
                path = Path(directory) / f"player{idx}.py"
                with path.open("wb") as dest:
                    for chunk in upload.chunks(): dest.write(chunk)
                paths.append(path)
            result = MatchManager().run(*paths, preset=preset, max_plies=max_plies, timeout=timeout)
    except (ValueError, OSError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    MATCHES[result["id"]] = result
    return JsonResponse({"match_id": result["id"], "status": result["status"], "ply": result["ply"], "result": result["result"]}, status=201)

@require_GET
def demo_match_detail(request, match_id):
    result = MATCHES.get(match_id)
    if not result: return JsonResponse({"error": "Không tìm thấy trận đấu."}, status=404)
    return JsonResponse(result)

@require_GET
def demo_match_state(request, match_id):
    result = MATCHES.get(match_id)
    if not result: return JsonResponse({"error": "Không tìm thấy trận đấu."}, status=404)
    return JsonResponse(result["state"])

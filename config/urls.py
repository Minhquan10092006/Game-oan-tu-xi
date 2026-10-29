"""
URL configuration cho toàn bộ project.
"""
import sys
import traceback
from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse, HttpResponse
from web.views import rooms_api


def health_check(request):
    return JsonResponse({'status': 'ok'})


def custom_500(request):
    t, v, tb = sys.exc_info()
    tb_str = "".join(traceback.format_exception(t, v, tb)) if t else "No traceback available."
    html = f"""<!DOCTYPE html>
<html>
<head><title>500 Server Error</title></head>
<body style="font-family: monospace; padding: 25px; background: #0f172a; color: #f87171; line-height: 1.6;">
    <h2 style="color: #ef4444; border-bottom: 1px solid #334155; padding-bottom: 10px;">⚠️ Django 500 Diagnostic Info</h2>
    <p style="color: #94a3b8;">Lỗi chi tiết bên dưới giúp xác định nguyên nhân:</p>
    <pre style="background: #1e293b; padding: 18px; border-radius: 8px; overflow-x: auto; color: #e2e8f0; border: 1px solid #475569;">{tb_str}</pre>
</body>
</html>"""
    return HttpResponse(html, status=500)


handler500 = custom_500

urlpatterns = [
    path('health/', health_check, name='health'),
    path('', include('web.urls')),
    path('api/rooms/', rooms_api, name='rooms-api'),
    path('api/ranking/', include('web.api_urls')),
    path('api/matches/', include('matches.urls')),
    path('api/submissions/', include('submissions.urls')),
    path('api/competition/', include('web.competition_urls')),
]

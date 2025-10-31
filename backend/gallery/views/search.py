from math import radians, cos, sin, asin, sqrt

from django.db.models import Count, Max, Q
from django.db.models.functions import TruncMonth
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Photo
from ..serializers import PhotoSerializer

def haversine(lat1, lon1, lat2, lon2):
    # 返回两点距离（km）
    R = 6371
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon/2)**2
    return 2 * R * asin(sqrt(a))

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def search_photos(request):
    """智能搜索接口"""
    user = request.user
    qs = Photo.objects.filter(owner=user)

    q = request.query_params.get("q")
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(tags__name__icontains=q)
            | Q(camera_make__icontains=q)
            | Q(camera_model__icontains=q)
        ).distinct()

    start_date = request.query_params.get("start_date")
    end_date = request.query_params.get("end_date")
    if start_date:
        qs = qs.filter(taken_at__gte=start_date)
    if end_date:
        qs = qs.filter(taken_at__lte=end_date)

    camera = request.query_params.get("camera")
    if camera:
        qs = qs.filter(Q(camera_make__icontains=camera) | Q(camera_model__icontains=camera))

    tag_id = request.query_params.get("tag_id")
    if tag_id:
        qs = qs.filter(tags__id=tag_id)

    album_id = request.query_params.get("album_id")
    if album_id:
        qs = qs.filter(album_id=album_id)

    # GPS过滤（圆形范围）
    lat = request.query_params.get("lat")
    lng = request.query_params.get("lng")
    radius = request.query_params.get("radius")  # 单位：公里
    if lat and lng and radius:
        lat = float(lat)
        lng = float(lng)
        radius = float(radius)
        nearby_ids = []
        for p in qs.filter(gps_lat__isnull=False, gps_lng__isnull=False):
            if haversine(lat, lng, p.gps_lat, p.gps_lng) <= radius:
                nearby_ids.append(p.id)
        qs = qs.filter(id__in=nearby_ids)

    qs = qs.order_by("-taken_at", "-uploaded_at")[:500]
    return Response(PhotoSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def timeline_photos(request):
    """按年月分组统计"""
    user = request.user
    data = (
        Photo.objects.filter(owner=user)
        .exclude(taken_at__isnull=True)
        .annotate(month=TruncMonth("taken_at"))
        .values("month")
        .annotate(count=Count("id"), cover=Max("thumbnail"))
        .order_by("-month")
    )
    return Response(data)

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def map_points(request):
    """返回带坐标的聚合点"""
    user = request.user
    qs = Photo.objects.filter(owner=user, gps_lat__isnull=False, gps_lng__isnull=False)
    points = []
    for p in qs:
        points.append({
            "id": p.id,
            "lat": p.gps_lat,
            "lng": p.gps_lng,
            "thumbnail": p.thumbnail.url if p.thumbnail else None,
            "title": p.title,
        })
    return Response(points)

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def map_clusters(request):
    """简易聚合，按zoom级别聚类"""
    zoom = int(request.query_params.get("zoom", 8))
    cell_size = 360 / (2 ** zoom)  # 近似每格经度宽度
    user = request.user
    qs = Photo.objects.filter(owner=user, gps_lat__isnull=False, gps_lng__isnull=False)

    clusters = {}
    for p in qs:
        lat_idx = int(p.gps_lat / cell_size)
        lng_idx = int(p.gps_lng / cell_size)
        key = (lat_idx, lng_idx)
        clusters.setdefault(key, {"count": 0, "lat_sum": 0, "lng_sum": 0})
        clusters[key]["count"] += 1
        clusters[key]["lat_sum"] += p.gps_lat
        clusters[key]["lng_sum"] += p.gps_lng

    result = []
    for (k, v) in clusters.items():
        result.append({
            "lat": v["lat_sum"] / v["count"],
            "lng": v["lng_sum"] / v["count"],
            "count": v["count"],
        })

    return Response(result)

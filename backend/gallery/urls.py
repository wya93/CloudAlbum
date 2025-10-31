from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AlbumViewSet,
    PhotoViewSet,
    TagViewSet,
    auto_by_face,
    auto_by_label,
    map_clusters,
    map_points,
    memories_today,
    public_share_view,
    search_photos,
    similar_photos,
    timeline_photos,
)

router = DefaultRouter()
router.register("albums", AlbumViewSet, basename="album")
router.register("photos", PhotoViewSet, basename="photo")
router.register("tags", TagViewSet, basename="tag")

urlpatterns = router.urls + [
    path("share/<str:token>/", public_share_view),
    path("search/", search_photos),
    path("timeline/", timeline_photos),
    path("map_points/", map_points),
    path("map_clusters/", map_clusters),
    path("photos/<int:photo_id>/similar/", similar_photos),
    path("memories/today/", memories_today),
    path("auto_albums/by_label/", auto_by_label),
    path("auto_albums/by_face/", auto_by_face),
]

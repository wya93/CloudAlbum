from rest_framework.routers import DefaultRouter
from .views import AlbumViewSet, PhotoViewSet, TagViewSet
from .views import public_share_view
from django.urls import path
from .views_search import search_photos, timeline_photos, map_points, map_clusters
from .views_recommend import similar_photos, memories_today
from .views_auto import auto_by_label, auto_by_face  # 可按你喜好组织

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

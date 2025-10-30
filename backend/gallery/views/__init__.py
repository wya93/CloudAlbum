"""View entrypoints aggregated for router imports."""

from .auto import auto_by_face, auto_by_label
from .base import AlbumViewSet, PhotoViewSet, TagViewSet, public_share_view
from .recommend import memories_today, similar_photos
from .search import map_clusters, map_points, search_photos, timeline_photos

__all__ = [
    "AlbumViewSet",
    "PhotoViewSet",
    "TagViewSet",
    "public_share_view",
    "auto_by_label",
    "auto_by_face",
    "search_photos",
    "timeline_photos",
    "map_points",
    "map_clusters",
    "similar_photos",
    "memories_today",
]


from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.deps import DbSession, OptionalSubscriber
from app.models.cdn import CDNNode
from app.models.content import Episode, Movie
from app.schemas.media import StreamManifest
from app.services.hls import hls_dir, public_playlist_url, write_placeholder_package

router = APIRouter(tags=["stream"])


@router.get("/stream/{content_type}/{content_id}", response_model=StreamManifest)
def get_stream_manifest(
    content_type: str,
    content_id: int,
    db: DbSession,
    _: OptionalSubscriber,
    episode_id: int | None = Query(None),
):
    if content_type not in {"movie", "series", "episode"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content type")

    title = ""
    qualities = ["1080p", "720p", "480p", "360p"]
    hls_path = None

    if content_type == "movie":
        movie = db.get(Movie, content_id)
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        title = movie.title
        qualities = movie.qualities or qualities
        hls_path = movie.hls_path
        if not hls_path:
            hls_path = write_placeholder_package("movie", movie.id, qualities)
            movie.hls_path = hls_path
            db.add(movie)
            db.commit()
        content_type_key = "movie"
        resolved_id = movie.id
        ep_id = None
    elif content_type == "episode":
        episode = db.get(Episode, content_id)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        title = episode.title
        hls_path = episode.hls_path
        if not hls_path:
            hls_path = write_placeholder_package("episode", episode.id, qualities)
            episode.hls_path = hls_path
            db.add(episode)
            db.commit()
        content_type_key = "episode"
        resolved_id = episode.id
        ep_id = None
    else:
        # series + optional episode
        if episode_id is None:
            raise HTTPException(status_code=400, detail="episode_id required for series streams")
        episode = db.get(Episode, episode_id)
        if not episode or episode.series_id != content_id:
            raise HTTPException(status_code=404, detail="Episode not found")
        title = episode.title
        hls_path = episode.hls_path
        if not hls_path:
            hls_path = write_placeholder_package("series", content_id, qualities, episode_id=episode.id)
            episode.hls_path = hls_path
            db.add(episode)
            db.commit()
        content_type_key = "series"
        resolved_id = content_id
        ep_id = episode.id

    node = (
        db.query(CDNNode)
        .filter(CDNNode.status == "online")
        .order_by(CDNNode.health_score.desc())
        .first()
    )
    return StreamManifest(
        content_type=content_type_key,
        content_id=resolved_id,
        episode_id=ep_id,
        title=title,
        qualities=qualities,
        playlist_url=public_playlist_url(content_type_key, resolved_id, ep_id),
        cdn_node=node.name if node else "Origin",
        skip_intro_seconds=0,
    )


@router.get("/media/hls/{path:path}")
def serve_hls(path: str):
    target = (hls_dir() / path).resolve()
    root = hls_dir().resolve()
    if not str(target).startswith(str(root)) or not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Media not found")
    media_type = "application/vnd.apple.mpegurl" if target.suffix == ".m3u8" else "video/mp2t"
    return FileResponse(target, media_type=media_type)

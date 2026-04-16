import os
import random
import string
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy import text, or_, and_
from werkzeug.utils import secure_filename

load_dotenv()

from models import LibraryEntry, User, FavoriteArtist, FavoriteSong, FriendRequest, db
import spotify as sp
import github_storage as gs

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
_db_url = os.environ.get("DATABASE_URL", "sqlite:///spotilist.db")
# Normalise Render/Heroku "postgres://" shorthand
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
# Use psycopg3 dialect (psycopg[binary]) instead of psycopg2
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _unique_friend_code():
    """Generate a unique 8-char friend code."""
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not User.query.filter_by(friend_code=code).first():
            return code


def _store_image(file_storage, path_prefix: str) -> str | None:
    """
    Save an uploaded image file.
    Uses GitHub storage if configured, otherwise local static/uploads/.
    Returns the public URL, or None on failure.
    """
    if not file_storage or not allowed_file(file_storage.filename):
        return None

    file_bytes = file_storage.read()
    ext = file_storage.filename.rsplit(".", 1)[1].lower() if "." in file_storage.filename else "jpg"

    if gs.is_configured():
        return gs.upload(file_bytes, f"images/{path_prefix}.{ext}")

    # Local fallback
    filename = secure_filename(f"{path_prefix}.{ext}")
    upload_dir = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    with open(os.path.join(upload_dir, filename), "wb") as f:
        f.write(file_bytes)
    return url_for("static", filename=f"uploads/{filename}")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)


with app.app_context():
    db.create_all()

    # Migrate: add new columns to existing tables (SQLite safe — ignores if already exists)
    with db.engine.connect() as conn:
        migrations = [
            ("users",           "banner_image VARCHAR"),
            ("users",           "custom_image VARCHAR"),
            ("users",           "friend_code VARCHAR(8)"),
            ("library_entries", "track_count INTEGER"),
        ]
        for table, col_def in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_def}"))
                conn.commit()
            except Exception:
                pass

    # Assign friend codes to existing users that don't have one
    users_without_code = User.query.filter(User.friend_code.is_(None)).all()
    for u in users_without_code:
        u.friend_code = _unique_friend_code()
    if users_without_code:
        db.session.commit()


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


# ---------------------------------------------------------------------------
# Spotify OAuth
# ---------------------------------------------------------------------------

@app.route("/auth/spotify")
def auth_spotify():
    return redirect(sp.get_auth_url())


@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error or not code:
        return redirect(url_for("login"))

    tokens = sp.exchange_code(code)
    if "access_token" not in tokens:
        return redirect(url_for("login"))

    profile = sp.get_user_profile(tokens["access_token"])
    spotify_id = profile.get("id")
    if not spotify_id:
        return redirect(url_for("login"))

    import time
    user = User.query.filter_by(spotify_id=spotify_id).first()
    images = profile.get("images") or []
    image_url = images[0].get("url") if images else None

    if not user:
        user = User(
            spotify_id=spotify_id,
            name=profile.get("display_name"),
            email=profile.get("email"),
            image=image_url,
            friend_code=_unique_friend_code(),
        )
        db.session.add(user)
    else:
        user.name = profile.get("display_name")
        user.email = profile.get("email")
        if image_url:
            user.image = image_url
        if not user.friend_code:
            user.friend_code = _unique_friend_code()

    user.access_token = tokens["access_token"]
    user.refresh_token = tokens.get("refresh_token")
    user.token_expires_at = int(time.time()) + tokens.get("expires_in", 3600)
    db.session.commit()
    login_user(user)
    return redirect(url_for("dashboard"))


@app.route("/auth/logout")
@login_required
def auth_logout():
    logout_user()
    return redirect(url_for("landing"))


# ---------------------------------------------------------------------------
# Protected pages
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    token = sp.get_valid_token(current_user)

    rp_data = sp.recently_played(token, limit=50)
    seen = set()
    recently_played_tracks = []
    for item in rp_data.get("items", []):
        track = item.get("track")
        if not track or track["id"] in seen:
            continue
        seen.add(track["id"])
        recently_played_tracks.append(track)

    existing_ids = {
        row.spotify_id
        for row in LibraryEntry.query.filter_by(user_id=current_user.id)
        .with_entities(LibraryEntry.spotify_id)
    }
    new_entries = []
    for track in recently_played_tracks:
        if track["id"] not in existing_ids:
            artist = ", ".join(a["name"] for a in track.get("artists", []))
            images = track.get("album", {}).get("images", [])
            new_entries.append(LibraryEntry(
                user_id=current_user.id,
                spotify_id=track["id"],
                type="track",
                name=track["name"],
                artist=artist,
                image_url=images[0]["url"] if images else None,
                release_date=track.get("album", {}).get("release_date"),
                spotify_url=track.get("external_urls", {}).get("spotify"),
                duration_ms=track.get("duration_ms"),
                status="completed",
            ))
    if new_entries:
        db.session.add_all(new_entries)
        db.session.commit()

    entries = (
        LibraryEntry.query.filter_by(user_id=current_user.id)
        .order_by(LibraryEntry.created_at.desc())
        .all()
    )
    total = len(entries)
    by_status = {}
    for e in entries:
        by_status[e.status] = by_status.get(e.status, 0) + 1

    rated = [e for e in entries if e.rating]
    avg_rating = round(sum(e.rating for e in rated) / len(rated), 1) if rated else None
    in_library = {e.spotify_id for e in entries}

    return render_template(
        "dashboard.html",
        total=total,
        by_status=by_status,
        avg_rating=avg_rating,
        recent=entries[:6],
        recently_played=recently_played_tracks,
        in_library=in_library,
    )


@app.route("/search")
@login_required
def search():
    return render_template("search.html")


@app.route("/library")
@login_required
def library():
    status_filter = request.args.get("status", "")
    type_filter = request.args.get("type", "")
    query = LibraryEntry.query.filter_by(user_id=current_user.id)
    if status_filter:
        query = query.filter_by(status=status_filter)
    if type_filter:
        query = query.filter_by(type=type_filter)
    entries = query.order_by(LibraryEntry.created_at.desc()).all()
    return render_template(
        "library.html",
        entries=entries,
        status_filter=status_filter,
        type_filter=type_filter,
    )


@app.route("/profile")
@login_required
def profile():
    entries = LibraryEntry.query.filter_by(user_id=current_user.id).all()
    track_entries = sum(1 for e in entries if e.type == "track")
    album_track_sum = sum(
        e.track_count or 0
        for e in entries
        if e.type == "album" and e.status == "completed"
    )
    total_tracks = track_entries + album_track_sum
    total_albums = sum(1 for e in entries if e.type == "album")
    plan_to_listen = sum(1 for e in entries if e.status == "plan_to_listen")
    completed = sum(1 for e in entries if e.status == "completed")
    rated = [e for e in entries if e.rating]
    avg_rating = round(sum(e.rating for e in rated) / len(rated), 1) if rated else None
    hours = round(
        sum(e.duration_ms or 0 for e in entries if e.type == "track") / 3_600_000, 1
    )
    fav_artists = {
        fa.position: fa
        for fa in FavoriteArtist.query.filter_by(user_id=current_user.id).all()
    }
    fav_songs = {
        fs.position: fs
        for fs in FavoriteSong.query.filter_by(user_id=current_user.id).all()
    }
    friend_count = FriendRequest.query.filter(
        FriendRequest.status == "accepted",
        or_(FriendRequest.sender_id == current_user.id, FriendRequest.receiver_id == current_user.id)
    ).count()
    return render_template(
        "profile.html",
        total_tracks=total_tracks,
        total_albums=total_albums,
        plan_to_listen=plan_to_listen,
        completed=completed,
        avg_rating=avg_rating,
        hours=hours,
        fav_artists=fav_artists,
        fav_songs=fav_songs,
        friend_count=friend_count,
    )


@app.route("/user/<user_id>")
@login_required
def user_profile(user_id):
    """Public view of a user's profile (only accessible if friends)."""
    target = User.query.get_or_404(user_id)
    if target.id == current_user.id:
        return redirect(url_for("profile"))

    # Only friends can view each other's profiles
    is_friend = FriendRequest.query.filter(
        FriendRequest.status == "accepted",
        or_(
            and_(FriendRequest.sender_id == current_user.id,   FriendRequest.receiver_id == target.id),
            and_(FriendRequest.sender_id == target.id,         FriendRequest.receiver_id == current_user.id),
        )
    ).first()
    if not is_friend:
        return redirect(url_for("friends"))

    entries = LibraryEntry.query.filter_by(user_id=target.id).all()
    track_entries = sum(1 for e in entries if e.type == "track")
    album_track_sum = sum(
        e.track_count or 0
        for e in entries
        if e.type == "album" and e.status == "completed"
    )
    total_tracks = track_entries + album_track_sum
    total_albums = sum(1 for e in entries if e.type == "album")
    plan_to_listen = sum(1 for e in entries if e.status == "plan_to_listen")
    completed = sum(1 for e in entries if e.status == "completed")
    rated = [e for e in entries if e.rating]
    avg_rating = round(sum(e.rating for e in rated) / len(rated), 1) if rated else None
    hours = round(
        sum(e.duration_ms or 0 for e in entries if e.type == "track") / 3_600_000, 1
    )
    fav_artists = {
        fa.position: fa
        for fa in FavoriteArtist.query.filter_by(user_id=target.id).all()
    }
    fav_songs = {
        fs.position: fs
        for fs in FavoriteSong.query.filter_by(user_id=target.id).all()
    }

    # Friend count for target user
    friend_count = FriendRequest.query.filter(
        FriendRequest.status == "accepted",
        or_(FriendRequest.sender_id == target.id, FriendRequest.receiver_id == target.id)
    ).count()

    # Recent library entries (completed + rated)
    recent_entries = (
        LibraryEntry.query.filter_by(user_id=target.id)
        .order_by(LibraryEntry.updated_at.desc())
        .limit(6)
        .all()
    )

    return render_template(
        "user_profile.html",
        target=target,
        total_tracks=total_tracks,
        total_albums=total_albums,
        plan_to_listen=plan_to_listen,
        completed=completed,
        avg_rating=avg_rating,
        hours=hours,
        fav_artists=fav_artists,
        fav_songs=fav_songs,
        friend_count=friend_count,
        recent_entries=recent_entries,
    )


@app.route("/friends")
@login_required
def friends():
    # Accepted friendships (either direction)
    accepted = FriendRequest.query.filter(
        or_(
            and_(FriendRequest.sender_id == current_user.id,   FriendRequest.status == "accepted"),
            and_(FriendRequest.receiver_id == current_user.id, FriendRequest.status == "accepted"),
        )
    ).all()

    friend_ids = []
    for fr in accepted:
        fid = fr.receiver_id if fr.sender_id == current_user.id else fr.sender_id
        friend_ids.append(fid)

    friend_users = User.query.filter(User.id.in_(friend_ids)).all() if friend_ids else []

    # Pending incoming requests
    incoming = FriendRequest.query.filter_by(
        receiver_id=current_user.id, status="pending"
    ).all()

    # Pending outgoing requests
    outgoing = FriendRequest.query.filter_by(
        sender_id=current_user.id, status="pending"
    ).all()

    # Activity feed: friends' recent library activity (ratings / completions)
    activity = []
    if friend_ids:
        activity = (
            LibraryEntry.query.filter(
                LibraryEntry.user_id.in_(friend_ids),
                LibraryEntry.rating.isnot(None),
            )
            .order_by(LibraryEntry.updated_at.desc())
            .limit(30)
            .all()
        )

    # Map user_id → User for activity display
    friend_map = {u.id: u for u in friend_users}

    return render_template(
        "friends.html",
        friend_users=friend_users,
        incoming=incoming,
        outgoing=outgoing,
        activity=activity,
        friend_map=friend_map,
    )


# ---------------------------------------------------------------------------
# API: Spotify proxy
# ---------------------------------------------------------------------------

@app.route("/api/spotify/search")
@login_required
def api_spotify_search():
    q = request.args.get("q", "").strip()
    types = request.args.get("types", "album,track")
    if not q:
        return jsonify({"albums": {"items": []}, "tracks": {"items": []}, "artists": {"items": []}})
    token = sp.get_valid_token(current_user)
    results = sp.search(token, q, types)
    return jsonify(results)


@app.route("/api/spotify/recently-played")
@login_required
def api_recently_played():
    token = sp.get_valid_token(current_user)
    return jsonify(sp.recently_played(token))


@app.route("/api/spotify/currently-playing")
@login_required
def api_currently_playing():
    token = sp.get_valid_token(current_user)
    return jsonify(sp.currently_playing(token))


# ---------------------------------------------------------------------------
# API: Library CRUD
# ---------------------------------------------------------------------------

def _entry_dict(e):
    return {
        "id": e.id,
        "spotifyId": e.spotify_id,
        "type": e.type,
        "name": e.name,
        "artist": e.artist,
        "imageUrl": e.image_url,
        "releaseDate": e.release_date,
        "spotifyUrl": e.spotify_url,
        "durationMs": e.duration_ms,
        "trackCount": e.track_count,
        "status": e.status,
        "rating": e.rating,
        "review": e.review,
        "createdAt": e.created_at.isoformat() if e.created_at else None,
    }


@app.route("/api/library", methods=["GET"])
@login_required
def api_library_get():
    status = request.args.get("status", "")
    type_ = request.args.get("type", "")
    q = LibraryEntry.query.filter_by(user_id=current_user.id)
    if status:
        q = q.filter_by(status=status)
    if type_:
        q = q.filter_by(type=type_)
    entries = q.order_by(LibraryEntry.created_at.desc()).all()
    return jsonify([_entry_dict(e) for e in entries])


@app.route("/api/library", methods=["POST"])
@login_required
def api_library_post():
    data = request.get_json(force=True)
    existing = LibraryEntry.query.filter_by(
        user_id=current_user.id, spotify_id=data["spotifyId"]
    ).first()

    if existing:
        existing.status = data.get("status", existing.status)
        existing.rating = data.get("rating") or existing.rating
        existing.review = data.get("review", existing.review)
        if data.get("totalTracks") and existing.track_count is None:
            existing.track_count = data["totalTracks"]
        existing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify(_entry_dict(existing))

    entry = LibraryEntry(
        user_id=current_user.id,
        spotify_id=data["spotifyId"],
        type=data["type"],
        name=data["name"],
        artist=data["artist"],
        image_url=data.get("imageUrl"),
        release_date=data.get("releaseDate"),
        spotify_url=data.get("spotifyUrl"),
        duration_ms=data.get("durationMs"),
        track_count=data.get("totalTracks"),
        status=data.get("status", "plan_to_listen"),
        rating=data.get("rating"),
        review=data.get("review"),
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify(_entry_dict(entry)), 201


@app.route("/api/library/<entry_id>", methods=["PATCH"])
@login_required
def api_library_patch(entry_id):
    entry = LibraryEntry.query.filter_by(
        id=entry_id, user_id=current_user.id
    ).first_or_404()
    data = request.get_json(force=True)
    if "status" in data:
        entry.status = data["status"]
    if "rating" in data:
        entry.rating = data["rating"]
    if "review" in data:
        entry.review = data["review"]
    entry.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_entry_dict(entry))


@app.route("/api/library/<entry_id>", methods=["DELETE"])
@login_required
def api_library_delete(entry_id):
    entry = LibraryEntry.query.filter_by(
        id=entry_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# API: Profile image upload
# ---------------------------------------------------------------------------

@app.route("/api/profile/picture", methods=["POST"])
@login_required
def api_profile_picture():
    url = _store_image(request.files.get("file"), f"pfp_{current_user.id}")
    if not url:
        return jsonify({"error": "Invalid file"}), 400
    current_user.custom_image = url
    db.session.commit()
    return jsonify({"imageUrl": url})


@app.route("/api/profile/banner", methods=["POST"])
@login_required
def api_profile_banner():
    url = _store_image(request.files.get("file"), f"banner_{current_user.id}")
    if not url:
        return jsonify({"error": "Invalid file"}), 400
    current_user.banner_image = url
    db.session.commit()
    return jsonify({"bannerUrl": url})


# ---------------------------------------------------------------------------
# API: Favorite artists / songs
# ---------------------------------------------------------------------------

@app.route("/api/favorites/artists/<int:position>", methods=["PUT", "DELETE"])
@login_required
def api_favorite_artist(position):
    if position not in range(1, 5):
        return jsonify({"error": "Position must be 1-4"}), 400
    if request.method == "DELETE":
        FavoriteArtist.query.filter_by(user_id=current_user.id, position=position).delete()
        db.session.commit()
        return jsonify({"success": True})
    data = request.get_json(force=True)
    fa = FavoriteArtist.query.filter_by(user_id=current_user.id, position=position).first()
    if fa:
        fa.spotify_id = data["spotifyId"]
        fa.name = data["name"]
        fa.image_url = data.get("imageUrl")
        fa.spotify_url = data.get("spotifyUrl")
    else:
        db.session.add(FavoriteArtist(
            user_id=current_user.id, position=position,
            spotify_id=data["spotifyId"], name=data["name"],
            image_url=data.get("imageUrl"), spotify_url=data.get("spotifyUrl"),
        ))
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/favorites/songs/<int:position>", methods=["PUT", "DELETE"])
@login_required
def api_favorite_song(position):
    if position not in range(1, 5):
        return jsonify({"error": "Position must be 1-4"}), 400
    if request.method == "DELETE":
        FavoriteSong.query.filter_by(user_id=current_user.id, position=position).delete()
        db.session.commit()
        return jsonify({"success": True})
    data = request.get_json(force=True)
    fs = FavoriteSong.query.filter_by(user_id=current_user.id, position=position).first()
    if fs:
        fs.spotify_id = data["spotifyId"]
        fs.name = data["name"]
        fs.artist = data["artist"]
        fs.image_url = data.get("imageUrl")
        fs.spotify_url = data.get("spotifyUrl")
        fs.duration_ms = data.get("durationMs")
    else:
        db.session.add(FavoriteSong(
            user_id=current_user.id, position=position,
            spotify_id=data["spotifyId"], name=data["name"],
            artist=data["artist"], image_url=data.get("imageUrl"),
            spotify_url=data.get("spotifyUrl"), duration_ms=data.get("durationMs"),
        ))
    db.session.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# API: Friends
# ---------------------------------------------------------------------------

@app.route("/api/friends/request", methods=["POST"])
@login_required
def api_friend_request():
    data = request.get_json(force=True)
    code = (data.get("friendCode") or "").strip().upper()
    if not code:
        return jsonify({"error": "Friend code required"}), 400

    target = User.query.filter_by(friend_code=code).first()
    if not target:
        return jsonify({"error": "No user found with that friend code"}), 404
    if target.id == current_user.id:
        return jsonify({"error": "That's your own code!"}), 400

    # Check for existing relationship
    existing = FriendRequest.query.filter(
        or_(
            and_(FriendRequest.sender_id == current_user.id, FriendRequest.receiver_id == target.id),
            and_(FriendRequest.sender_id == target.id, FriendRequest.receiver_id == current_user.id),
        )
    ).first()

    if existing:
        if existing.status == "accepted":
            return jsonify({"error": "Already friends"}), 400
        if existing.status == "pending":
            # If they already sent us a request, auto-accept
            if existing.receiver_id == current_user.id:
                existing.status = "accepted"
                db.session.commit()
                return jsonify({"status": "accepted", "name": target.name})
            return jsonify({"error": "Request already sent"}), 400

    fr = FriendRequest(sender_id=current_user.id, receiver_id=target.id)
    db.session.add(fr)
    db.session.commit()
    return jsonify({"status": "pending", "name": target.name})


@app.route("/api/friends/respond/<request_id>", methods=["POST"])
@login_required
def api_friend_respond(request_id):
    fr = FriendRequest.query.filter_by(
        id=request_id, receiver_id=current_user.id, status="pending"
    ).first_or_404()
    action = request.get_json(force=True).get("action")  # "accept" or "decline"
    if action == "accept":
        fr.status = "accepted"
    elif action == "decline":
        fr.status = "declined"
    else:
        return jsonify({"error": "Invalid action"}), 400
    db.session.commit()
    return jsonify({"success": True, "status": fr.status})


@app.route("/api/friends/remove/<friend_id>", methods=["DELETE"])
@login_required
def api_friend_remove(friend_id):
    fr = FriendRequest.query.filter(
        FriendRequest.status == "accepted",
        or_(
            and_(FriendRequest.sender_id == current_user.id, FriendRequest.receiver_id == friend_id),
            and_(FriendRequest.sender_id == friend_id, FriendRequest.receiver_id == current_user.id),
        )
    ).first_or_404()
    db.session.delete(fr)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/friends/now-playing/<friend_id>")
@login_required
def api_friend_now_playing(friend_id):
    """Return currently playing or most recent track for a friend."""
    # Verify friendship
    is_friend = FriendRequest.query.filter(
        FriendRequest.status == "accepted",
        or_(
            and_(FriendRequest.sender_id == current_user.id,   FriendRequest.receiver_id == friend_id),
            and_(FriendRequest.sender_id == friend_id,         FriendRequest.receiver_id == current_user.id),
        )
    ).first()
    if not is_friend:
        return jsonify({"error": "Not friends"}), 403

    friend = User.query.get_or_404(friend_id)
    try:
        token = sp.get_valid_token(friend)
        current = sp.currently_playing(token)
        if current and current.get("item"):
            return jsonify({"track": current["item"], "is_playing": current.get("is_playing", False)})
        # Fall back to most recently played
        rp = sp.recently_played(token, limit=1)
        items = rp.get("items", [])
        if items:
            return jsonify({"recent": items[0]["track"]})
    except Exception:
        pass
    return jsonify({})


@app.route("/api/friends/all-activity")
@login_required
def api_friends_all_activity():
    """Return now-playing or most-recent track for all friends (for friends page)."""
    accepted = FriendRequest.query.filter(
        or_(
            and_(FriendRequest.sender_id == current_user.id,   FriendRequest.status == "accepted"),
            and_(FriendRequest.receiver_id == current_user.id, FriendRequest.status == "accepted"),
        )
    ).all()
    friend_ids = [
        fr.receiver_id if fr.sender_id == current_user.id else fr.sender_id
        for fr in accepted
    ]
    result = {}
    for fid in friend_ids:
        friend = User.query.get(fid)
        if not friend or not friend.access_token:
            continue
        try:
            token = sp.get_valid_token(friend)
            current = sp.currently_playing(token)
            if current and current.get("item"):
                result[fid] = {"track": current["item"], "is_playing": current.get("is_playing", False)}
                continue
            rp = sp.recently_played(token, limit=1)
            items = rp.get("items", [])
            if items:
                result[fid] = {"recent": items[0]["track"]}
        except Exception:
            pass
    return jsonify(result)


@app.route("/api/friends/pending-count")
@login_required
def api_pending_count():
    count = FriendRequest.query.filter_by(
        receiver_id=current_user.id, status="pending"
    ).count()
    return jsonify({"count": count})


# ---------------------------------------------------------------------------
# API: Spotify history import
# ---------------------------------------------------------------------------

@app.route("/api/library/import-history", methods=["POST"])
@login_required
def api_import_history():
    import json as _json

    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".json"):
        return jsonify({"error": "Please upload a JSON file"}), 400

    try:
        data = _json.loads(f.read())
    except Exception:
        return jsonify({"error": "Invalid JSON file"}), 400

    if not isinstance(data, list):
        return jsonify({"error": "Expected a JSON array"}), 400

    # Deduplicate unique tracks (skip podcasts / audiobooks with no track URI)
    seen = {}
    for item in data:
        uri = item.get("spotify_track_uri")
        name = item.get("master_metadata_track_name")
        artist = item.get("master_metadata_album_artist_name")
        if not uri or not name or not uri.startswith("spotify:track:"):
            continue
        if uri not in seen:
            seen[uri] = {"name": name, "artist": artist or ""}

    if not seen:
        return jsonify({"imported": 0, "skipped": 0,
                        "message": "No valid tracks found in file"}), 200

    # Determine which track IDs are already in the library
    existing_ids = {
        row.spotify_id
        for row in LibraryEntry.query.filter_by(user_id=current_user.id)
        .with_entities(LibraryEntry.spotify_id)
    }

    new_items = {
        uri: info for uri, info in seen.items()
        if uri.split(":")[-1] not in existing_ids
    }
    skipped = len(seen) - len(new_items)

    if not new_items:
        return jsonify({"imported": 0, "skipped": skipped,
                        "message": "All tracks already in library"}), 200

    # Batch-fetch full track details from Spotify (50 per request)
    token = sp.get_valid_token(current_user)
    track_id_list = [uri.split(":")[-1] for uri in new_items]
    track_details = {}
    for i in range(0, len(track_id_list), 50):
        batch = track_id_list[i:i + 50]
        try:
            track_details.update(sp.get_tracks(token, batch))
        except Exception:
            pass  # Fall back to search for this batch

    # Search fallback for tracks the batch lookup missed (removed/relinked tracks)
    missing_ids = [tid for tid in track_id_list if tid not in track_details]
    for track_id in missing_ids:
        uri_key = f"spotify:track:{track_id}"
        fb = new_items.get(uri_key, {})
        name, artist = fb.get("name", ""), fb.get("artist", "")
        if not name:
            continue
        try:
            results = sp.search(token, f"{name} {artist}", types="track", limit=1)
            items = results.get("tracks", {}).get("items", [])
            if items:
                track_details[track_id] = items[0]
        except Exception:
            pass

    new_entries = []
    for uri, fallback in new_items.items():
        track_id = uri.split(":")[-1]
        t = track_details.get(track_id)
        if t:
            artist = ", ".join(a["name"] for a in t.get("artists", []))
            images = t.get("album", {}).get("images", [])
            new_entries.append(LibraryEntry(
                user_id=current_user.id,
                spotify_id=track_id,
                type="track",
                name=t["name"],
                artist=artist,
                image_url=images[0]["url"] if images else None,
                release_date=t.get("album", {}).get("release_date"),
                spotify_url=t.get("external_urls", {}).get("spotify"),
                duration_ms=t.get("duration_ms"),
                status="completed",
            ))
        else:
            # Spotify lookup failed — store with data from the history file
            new_entries.append(LibraryEntry(
                user_id=current_user.id,
                spotify_id=track_id,
                type="track",
                name=fallback["name"],
                artist=fallback["artist"],
                spotify_url=f"https://open.spotify.com/track/{track_id}",
                status="completed",
            ))

    if new_entries:
        db.session.add_all(new_entries)
        db.session.commit()

    return jsonify({"imported": len(new_entries), "skipped": skipped})


@app.route("/api/library/refresh-art", methods=["POST"])
@login_required
def api_refresh_art():
    entries = (
        LibraryEntry.query
        .filter_by(user_id=current_user.id, type="track")
        .filter(LibraryEntry.image_url.is_(None))
        .all()
    )
    if not entries:
        return jsonify({"updated": 0, "message": "No tracks missing art"})

    token = sp.get_valid_token(current_user)
    entry_map = {e.spotify_id: e for e in entries}
    track_id_list = list(entry_map)

    # Batch lookup
    for i in range(0, len(track_id_list), 50):
        batch = track_id_list[i:i + 50]
        try:
            for track_id, t in sp.get_tracks(token, batch).items():
                entry = entry_map[track_id]
                images = t.get("album", {}).get("images", [])
                if images:
                    entry.image_url = images[0]["url"]
                entry.duration_ms = entry.duration_ms or t.get("duration_ms")
                entry.release_date = entry.release_date or t.get("album", {}).get("release_date")
                entry.spotify_url = entry.spotify_url or t.get("external_urls", {}).get("spotify")
        except Exception:
            pass

    # Search fallback for anything still missing
    for track_id, entry in entry_map.items():
        if entry.image_url:
            continue
        try:
            results = sp.search(token, f"{entry.name} {entry.artist}", types="track", limit=1)
            items = results.get("tracks", {}).get("items", [])
            if items:
                images = items[0].get("album", {}).get("images", [])
                if images:
                    entry.image_url = images[0]["url"]
        except Exception:
            pass

    updated = sum(1 for e in entries if e.image_url)
    if updated:
        db.session.commit()
    return jsonify({"updated": updated})


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

@app.template_filter("duration")
def duration_filter(ms):
    if not ms:
        return ""
    mins = ms // 60000
    secs = (ms % 60000) // 1000
    return f"{mins}:{secs:02d}"


if __name__ == "__main__":
    app.run(debug=True, port=8888)

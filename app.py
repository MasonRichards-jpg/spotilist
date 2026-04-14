import os
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
from sqlalchemy import text
from werkzeug.utils import secure_filename

load_dotenv()

from models import LibraryEntry, User, FavoriteArtist, FavoriteSong, db
import spotify as sp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///spotilist.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, user_id)


with app.app_context():
    db.create_all()
    # Migrate: add new columns to users table if they don't exist (SQLite safe)
    with db.engine.connect() as conn:
        for col in ["banner_image VARCHAR", "custom_image VARCHAR"]:
            try:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col}"))
                conn.commit()
            except Exception:
                pass  # Column already exists


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
        )
        db.session.add(user)
    else:
        user.name = profile.get("display_name")
        user.email = profile.get("email")
        if image_url:
            user.image = image_url

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

    # Fetch recently played (deduplicated)
    rp_data = sp.recently_played(token, limit=50)
    seen = set()
    recently_played_tracks = []
    for item in rp_data.get("items", []):
        track = item.get("track")
        if not track or track["id"] in seen:
            continue
        seen.add(track["id"])
        recently_played_tracks.append(track)

    # Auto-add any recently played tracks not yet in library as "completed"
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
                rating=None,
                review=None,
            ))
    if new_entries:
        db.session.add_all(new_entries)
        db.session.commit()

    # Query library (includes newly auto-added entries)
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


@app.route("/friends")
@login_required
def friends():
    return render_template("friends.html")


@app.route("/profile")
@login_required
def profile():
    entries = LibraryEntry.query.filter_by(user_id=current_user.id).all()
    total_tracks = sum(1 for e in entries if e.type == "track")
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
    results = sp.recently_played(token)
    return jsonify(results)


@app.route("/api/spotify/currently-playing")
@login_required
def api_currently_playing():
    token = sp.get_valid_token(current_user)
    data = sp.currently_playing(token)
    return jsonify(data)


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
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files["file"]
    if not file or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file"}), 400
    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(f"pfp_{current_user.id}.{ext}")
    upload_dir = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))
    current_user.custom_image = url_for("static", filename=f"uploads/{filename}")
    db.session.commit()
    return jsonify({"imageUrl": current_user.custom_image})


@app.route("/api/profile/banner", methods=["POST"])
@login_required
def api_profile_banner():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files["file"]
    if not file or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file"}), 400
    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(f"banner_{current_user.id}.{ext}")
    upload_dir = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))
    current_user.banner_image = url_for("static", filename=f"uploads/{filename}")
    db.session.commit()
    return jsonify({"bannerUrl": current_user.banner_image})


# ---------------------------------------------------------------------------
# API: Favorite artists
# ---------------------------------------------------------------------------


@app.route("/api/favorites/artists/<int:position>", methods=["PUT", "DELETE"])
@login_required
def api_favorite_artist(position):
    if position not in range(1, 5):
        return jsonify({"error": "Position must be 1-4"}), 400

    if request.method == "DELETE":
        FavoriteArtist.query.filter_by(
            user_id=current_user.id, position=position
        ).delete()
        db.session.commit()
        return jsonify({"success": True})

    data = request.get_json(force=True)
    fa = FavoriteArtist.query.filter_by(
        user_id=current_user.id, position=position
    ).first()
    if fa:
        fa.spotify_id = data["spotifyId"]
        fa.name = data["name"]
        fa.image_url = data.get("imageUrl")
        fa.spotify_url = data.get("spotifyUrl")
    else:
        fa = FavoriteArtist(
            user_id=current_user.id,
            position=position,
            spotify_id=data["spotifyId"],
            name=data["name"],
            image_url=data.get("imageUrl"),
            spotify_url=data.get("spotifyUrl"),
        )
        db.session.add(fa)
    db.session.commit()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# API: Favorite songs
# ---------------------------------------------------------------------------


@app.route("/api/favorites/songs/<int:position>", methods=["PUT", "DELETE"])
@login_required
def api_favorite_song(position):
    if position not in range(1, 5):
        return jsonify({"error": "Position must be 1-4"}), 400

    if request.method == "DELETE":
        FavoriteSong.query.filter_by(
            user_id=current_user.id, position=position
        ).delete()
        db.session.commit()
        return jsonify({"success": True})

    data = request.get_json(force=True)
    fs = FavoriteSong.query.filter_by(
        user_id=current_user.id, position=position
    ).first()
    if fs:
        fs.spotify_id = data["spotifyId"]
        fs.name = data["name"]
        fs.artist = data["artist"]
        fs.image_url = data.get("imageUrl")
        fs.spotify_url = data.get("spotifyUrl")
        fs.duration_ms = data.get("durationMs")
    else:
        fs = FavoriteSong(
            user_id=current_user.id,
            position=position,
            spotify_id=data["spotifyId"],
            name=data["name"],
            artist=data["artist"],
            image_url=data.get("imageUrl"),
            spotify_url=data.get("spotifyUrl"),
            duration_ms=data.get("durationMs"),
        )
        db.session.add(fs)
    db.session.commit()
    return jsonify({"success": True})


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

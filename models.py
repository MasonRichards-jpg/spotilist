from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid
import random
import string

db = SQLAlchemy()


def _uuid():
    return str(uuid.uuid4())


def generate_friend_code():
    """Generate a random 8-char uppercase alphanumeric code. Uniqueness enforced in app.py."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    spotify_id = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String)
    email = db.Column(db.String, unique=True)
    image = db.Column(db.String)
    banner_image = db.Column(db.String)
    custom_image = db.Column(db.String)
    friend_code = db.Column(db.String(8), unique=True)
    access_token = db.Column(db.String)
    refresh_token = db.Column(db.String)
    token_expires_at = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    library_entries = db.relationship(
        "LibraryEntry", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    favorite_artists = db.relationship(
        "FavoriteArtist", backref="user", lazy=True, cascade="all, delete-orphan",
        order_by="FavoriteArtist.position"
    )
    favorite_songs = db.relationship(
        "FavoriteSong", backref="user", lazy=True, cascade="all, delete-orphan",
        order_by="FavoriteSong.position"
    )
    sent_requests = db.relationship(
        "FriendRequest", foreign_keys="FriendRequest.sender_id",
        backref="sender", lazy=True, cascade="all, delete-orphan"
    )
    received_requests = db.relationship(
        "FriendRequest", foreign_keys="FriendRequest.receiver_id",
        backref="receiver", lazy=True, cascade="all, delete-orphan"
    )


class LibraryEntry(db.Model):
    __tablename__ = "library_entries"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    spotify_id = db.Column(db.String, nullable=False)
    type = db.Column(db.String, nullable=False)  # 'album' or 'track'
    name = db.Column(db.String, nullable=False)
    artist = db.Column(db.String, nullable=False)
    image_url = db.Column(db.String)
    release_date = db.Column(db.String)
    spotify_url = db.Column(db.String)
    duration_ms = db.Column(db.Integer)
    track_count = db.Column(db.Integer)   # albums only: number of tracks on the album
    status = db.Column(db.String, nullable=False, default="plan_to_listen")
    rating = db.Column(db.Integer)
    review = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "spotify_id", name="uq_user_spotify"),
    )


class FavoriteArtist(db.Model):
    __tablename__ = "favorite_artists"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False)  # 1-4
    spotify_id = db.Column(db.String, nullable=False)
    name = db.Column(db.String, nullable=False)
    image_url = db.Column(db.String)
    spotify_url = db.Column(db.String)

    __table_args__ = (
        db.UniqueConstraint("user_id", "position", name="uq_fav_artist_pos"),
    )


class FavoriteSong(db.Model):
    __tablename__ = "favorite_songs"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    user_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    position = db.Column(db.Integer, nullable=False)  # 1-4
    spotify_id = db.Column(db.String, nullable=False)
    name = db.Column(db.String, nullable=False)
    artist = db.Column(db.String, nullable=False)
    image_url = db.Column(db.String)
    spotify_url = db.Column(db.String)
    duration_ms = db.Column(db.Integer)

    __table_args__ = (
        db.UniqueConstraint("user_id", "position", name="uq_fav_song_pos"),
    )


class FriendRequest(db.Model):
    __tablename__ = "friend_requests"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    sender_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String, nullable=False, default="pending")  # pending/accepted/declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("sender_id", "receiver_id", name="uq_friend_req"),
    )

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()


def _uuid():
    return str(uuid.uuid4())


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.String, primary_key=True, default=_uuid)
    spotify_id = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String)
    email = db.Column(db.String, unique=True)
    image = db.Column(db.String)
    access_token = db.Column(db.String)
    refresh_token = db.Column(db.String)
    token_expires_at = db.Column(db.Integer)  # Unix timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    library_entries = db.relationship(
        "LibraryEntry", backref="user", lazy=True, cascade="all, delete-orphan"
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
    status = db.Column(db.String, nullable=False, default="plan_to_listen")
    rating = db.Column(db.Integer)
    review = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "spotify_id", name="uq_user_spotify"),
    )

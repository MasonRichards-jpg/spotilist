import os
import time
from urllib.parse import urlencode

import requests

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.environ.get(
    "SPOTIFY_REDIRECT_URI", "http://localhost:5000/auth/callback"
)
SPOTIFY_SCOPES = " ".join([
    "user-read-email",
    "user-read-recently-played",
    "user-top-read",
    "user-library-read",
    "user-read-playback-state",
])

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"


def get_auth_url():
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
    }
    return "https://accounts.spotify.com/authorize?" + urlencode(params)


def exchange_code(code):
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": SPOTIFY_REDIRECT_URI,
        },
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
    )
    return resp.json()


def _refresh_token(refresh_token):
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
    )
    return resp.json()


def get_valid_token(user):
    """Return a valid access token, refreshing if needed. Commits to DB."""
    if user.token_expires_at and user.token_expires_at > int(time.time()) + 60:
        return user.access_token

    from models import db

    data = _refresh_token(user.refresh_token)
    user.access_token = data["access_token"]
    user.token_expires_at = int(time.time()) + data.get("expires_in", 3600)
    if "refresh_token" in data:
        user.refresh_token = data["refresh_token"]
    db.session.commit()
    return user.access_token


def spotify_get(token, path_or_url, params=None):
    url = path_or_url if path_or_url.startswith("http") else API_BASE + path_or_url
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    return resp.json()


def get_user_profile(token):
    return spotify_get(token, "/me")


def search(token, query, types="album,track", limit=10):
    return spotify_get(token, "/search", {"q": query, "type": types, "limit": limit})


def recently_played(token, limit=50):
    return spotify_get(token, "/me/player/recently-played", {"limit": limit})


def currently_playing(token):
    url = API_BASE + "/me/player/currently-playing"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()

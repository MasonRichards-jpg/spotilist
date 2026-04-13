import { prisma } from "@/lib/prisma"

const SPOTIFY_API = "https://api.spotify.com/v1"
const SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

export interface SpotifyAlbum {
  id: string
  name: string
  artists: { name: string }[]
  images: { url: string; width: number; height: number }[]
  release_date: string
  total_tracks: number
  external_urls: { spotify: string }
  album_type: string
}

export interface SpotifyTrack {
  id: string
  name: string
  artists: { name: string }[]
  album: SpotifyAlbum
  duration_ms: number
  external_urls: { spotify: string }
  preview_url: string | null
}

export interface SpotifySearchResult {
  albums?: { items: SpotifyAlbum[] }
  tracks?: { items: SpotifyTrack[] }
}

async function refreshAccessToken(
  refreshToken: string
): Promise<{ access_token: string; expires_at: number } | null> {
  try {
    const res = await fetch(SPOTIFY_TOKEN_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Authorization: `Basic ${Buffer.from(
          `${process.env.SPOTIFY_CLIENT_ID}:${process.env.SPOTIFY_CLIENT_SECRET}`
        ).toString("base64")}`,
      },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        refresh_token: refreshToken,
      }),
    })

    if (!res.ok) return null

    const data = await res.json()
    return {
      access_token: data.access_token,
      expires_at: Math.floor(Date.now() / 1000) + data.expires_in,
    }
  } catch {
    return null
  }
}

export async function getValidAccessToken(userId: string): Promise<string | null> {
  const account = await prisma.account.findFirst({
    where: { userId, provider: "spotify" },
  })

  if (!account?.access_token) return null

  const nowInSeconds = Math.floor(Date.now() / 1000)
  const isExpired = account.expires_at ? account.expires_at < nowInSeconds + 60 : false

  if (!isExpired) return account.access_token

  if (!account.refresh_token) return null

  const refreshed = await refreshAccessToken(account.refresh_token)
  if (!refreshed) return null

  await prisma.account.update({
    where: { id: account.id },
    data: {
      access_token: refreshed.access_token,
      expires_at: refreshed.expires_at,
    },
  })

  return refreshed.access_token
}

export async function spotifySearch(
  token: string,
  query: string,
  types: string[] = ["album", "track"],
  limit = 20
): Promise<SpotifySearchResult> {
  const params = new URLSearchParams({
    q: query,
    type: types.join(","),
    limit: String(limit),
  })

  const res = await fetch(`${SPOTIFY_API}/search?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  })

  if (!res.ok) throw new Error("Spotify search failed")
  return res.json()
}

export async function getRecentlyPlayed(
  token: string,
  limit = 50
): Promise<{ items: { track: SpotifyTrack; played_at: string }[] }> {
  const res = await fetch(
    `${SPOTIFY_API}/me/player/recently-played?limit=${limit}`,
    { headers: { Authorization: `Bearer ${token}` } }
  )

  if (!res.ok) throw new Error("Failed to fetch recently played")
  return res.json()
}

export async function getAlbum(token: string, albumId: string): Promise<SpotifyAlbum> {
  const res = await fetch(`${SPOTIFY_API}/albums/${albumId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error("Failed to fetch album")
  return res.json()
}

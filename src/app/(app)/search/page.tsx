"use client"

import { useState, useCallback } from "react"
import { Search, Plus, Check, Loader2 } from "lucide-react"
import Image from "next/image"
import { AddToLibraryModal } from "@/components/add-to-library-modal"
import type { SpotifyAlbum, SpotifyTrack } from "@/lib/spotify"

type SearchType = "album" | "track"

interface LibraryEntry {
  id: string
  spotifyId: string
  status: string
  rating: number | null
  review: string | null
}

export default function SearchPage() {
  const [query, setQuery] = useState("")
  const [searchType, setSearchType] = useState<SearchType>("album")
  const [albums, setAlbums] = useState<SpotifyAlbum[]>([])
  const [tracks, setTracks] = useState<SpotifyTrack[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [libraryMap, setLibraryMap] = useState<Record<string, LibraryEntry>>({})
  const [modal, setModal] = useState<{
    item: Parameters<typeof AddToLibraryModal>[0]["item"]
    existing: LibraryEntry | null
  } | null>(null)

  const search = useCallback(async (q: string, type: SearchType) => {
    if (!q.trim()) return
    setLoading(true)
    setSearched(true)
    try {
      const res = await fetch(`/api/spotify/search?q=${encodeURIComponent(q)}&types=${type}`)
      const data = await res.json()
      if (type === "album") {
        setAlbums(data.albums?.items ?? [])
        setTracks([])
      } else {
        setTracks(data.tracks?.items ?? [])
        setAlbums([])
      }

      // Fetch library status for results
      const ids = type === "album"
        ? (data.albums?.items ?? []).map((a: SpotifyAlbum) => a.id)
        : (data.tracks?.items ?? []).map((t: SpotifyTrack) => t.id)

      if (ids.length > 0) {
        const libRes = await fetch("/api/library")
        const libData: LibraryEntry[] = await libRes.json()
        const map: Record<string, LibraryEntry> = {}
        libData.forEach((e) => { map[e.spotifyId] = e })
        setLibraryMap(map)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    search(query, searchType)
  }

  function openModal(item: Parameters<typeof AddToLibraryModal>[0]["item"]) {
    setModal({ item, existing: libraryMap[item.spotifyId] ?? null })
  }

  async function handleSave(data: { status: string; rating: number | null; review: string }) {
    if (!modal) return
    const res = await fetch("/api/library", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...modal.item, ...data }),
    })
    const entry = await res.json()
    setLibraryMap((prev) => ({ ...prev, [modal.item.spotifyId]: entry }))
  }

  const results = searchType === "album" ? albums : tracks

  return (
    <div className="p-8 max-w-6xl">
      <h1 className="text-3xl font-bold mb-6">Search</h1>

      {/* Search bar */}
      <form onSubmit={handleSubmit} className="flex gap-3 mb-6">
        <div className="flex-1 relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-spotify-muted" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search for ${searchType === "album" ? "albums" : "tracks"}...`}
            className="w-full bg-spotify-card rounded-full pl-12 pr-4 py-3 text-sm outline-none focus:ring-2 focus:ring-spotify-green placeholder:text-spotify-subtle"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="bg-spotify-green hover:bg-spotify-green-hover text-black font-bold px-6 py-3 rounded-full text-sm transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Search"}
        </button>
      </form>

      {/* Type toggle */}
      <div className="flex gap-2 mb-8">
        {(["album", "track"] as SearchType[]).map((type) => (
          <button
            key={type}
            onClick={() => {
              setSearchType(type)
              if (query) search(query, type)
            }}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors capitalize ${
              searchType === type
                ? "bg-white text-black"
                : "bg-spotify-card text-spotify-muted hover:text-white"
            }`}
          >
            {type === "album" ? "Albums" : "Tracks"}
          </button>
        ))}
      </div>

      {/* Results */}
      {loading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-spotify-green" />
        </div>
      ) : searched && results.length === 0 ? (
        <p className="text-spotify-muted text-center py-20">No results found.</p>
      ) : searchType === "album" ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {albums.map((album) => {
            const inLibrary = libraryMap[album.id]
            const item = {
              spotifyId: album.id,
              type: "album" as const,
              name: album.name,
              artist: album.artists.map((a) => a.name).join(", "),
              imageUrl: album.images[0]?.url,
              releaseDate: album.release_date,
              spotifyUrl: album.external_urls.spotify,
            }
            return (
              <div key={album.id} className="group bg-spotify-card hover:bg-spotify-card-hover rounded-xl p-4 transition-colors">
                <div className="relative aspect-square w-full rounded-lg overflow-hidden mb-3">
                  {album.images[0] ? (
                    <Image
                      src={album.images[0].url}
                      alt={album.name}
                      fill
                      className="object-cover"
                      sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
                    />
                  ) : (
                    <div className="w-full h-full bg-spotify-subtle flex items-center justify-center text-spotify-muted text-3xl">♪</div>
                  )}
                  <button
                    onClick={() => openModal(item)}
                    className="absolute bottom-2 right-2 w-10 h-10 bg-spotify-green hover:bg-spotify-green-hover text-black rounded-full flex items-center justify-center shadow-lg opacity-0 group-hover:opacity-100 translate-y-2 group-hover:translate-y-0 transition-all"
                  >
                    {inLibrary ? <Check className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-sm font-medium truncate">{album.name}</p>
                <p className="text-xs text-spotify-muted truncate">
                  {album.artists.map((a) => a.name).join(", ")}
                </p>
                {inLibrary && (
                  <p className="text-xs text-spotify-green mt-1 truncate">
                    {inLibrary.status.replace(/_/g, " ")}
                    {inLibrary.rating ? ` · ★ ${inLibrary.rating}` : ""}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="space-y-2">
          {tracks.map((track) => {
            const inLibrary = libraryMap[track.id]
            const item = {
              spotifyId: track.id,
              type: "track" as const,
              name: track.name,
              artist: track.artists.map((a) => a.name).join(", "),
              imageUrl: track.album.images[0]?.url,
              spotifyUrl: track.external_urls.spotify,
              durationMs: track.duration_ms,
            }
            return (
              <div
                key={track.id}
                className="group flex items-center gap-4 bg-spotify-card hover:bg-spotify-card-hover rounded-xl p-3 transition-colors"
              >
                <div className="relative w-12 h-12 rounded-lg overflow-hidden flex-shrink-0">
                  {track.album.images[0] ? (
                    <Image
                      src={track.album.images[0].url}
                      alt={track.name}
                      fill
                      className="object-cover"
                      sizes="48px"
                    />
                  ) : (
                    <div className="w-full h-full bg-spotify-subtle flex items-center justify-center text-spotify-muted">♪</div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{track.name}</p>
                  <p className="text-xs text-spotify-muted truncate">
                    {track.artists.map((a) => a.name).join(", ")} · {track.album.name}
                  </p>
                </div>
                {inLibrary && (
                  <span className="text-xs text-spotify-green hidden sm:block">
                    {inLibrary.status.replace(/_/g, " ")}
                  </span>
                )}
                <button
                  onClick={() => openModal(item)}
                  className="w-9 h-9 bg-spotify-green hover:bg-spotify-green-hover text-black rounded-full flex items-center justify-center flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  {inLibrary ? <Check className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                </button>
              </div>
            )
          })}
        </div>
      )}

      {!searched && (
        <div className="text-center py-20">
          <Search className="w-12 h-12 text-spotify-subtle mx-auto mb-4" />
          <p className="text-spotify-muted">Search the Spotify catalog to add music to your library.</p>
        </div>
      )}

      {/* Modal */}
      {modal && (
        <AddToLibraryModal
          item={modal.item}
          existingEntry={modal.existing}
          onClose={() => setModal(null)}
          onSave={handleSave}
        />
      )}
    </div>
  )
}

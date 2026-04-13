"use client"

import { useState, useEffect, useCallback } from "react"
import Image from "next/image"
import { Trash2, Pencil, Star } from "lucide-react"
import { AddToLibraryModal } from "@/components/add-to-library-modal"
import { STATUS_LABELS, STATUS_COLORS } from "@/lib/utils"
import { cn } from "@/lib/utils"

interface LibraryEntry {
  id: string
  spotifyId: string
  type: string
  name: string
  artist: string
  imageUrl: string | null
  releaseDate: string | null
  spotifyUrl: string | null
  durationMs: number | null
  status: string
  rating: number | null
  review: string | null
  createdAt: string
  updatedAt: string
}

const STATUS_TABS = [
  { value: "", label: "All" },
  { value: "listening", label: "Listening" },
  { value: "completed", label: "Completed" },
  { value: "plan_to_listen", label: "Plan to Listen" },
  { value: "dropped", label: "Dropped" },
]

export default function LibraryPage() {
  const [entries, setEntries] = useState<LibraryEntry[]>([])
  const [status, setStatus] = useState("")
  const [typeFilter, setTypeFilter] = useState("")
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<LibraryEntry | null>(null)

  const fetchEntries = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams()
    if (status) params.set("status", status)
    if (typeFilter) params.set("type", typeFilter)
    const res = await fetch(`/api/library?${params}`)
    const data = await res.json()
    setEntries(data)
    setLoading(false)
  }, [status, typeFilter])

  useEffect(() => {
    fetchEntries()
  }, [fetchEntries])

  async function handleUpdate(data: { status: string; rating: number | null; review: string }) {
    if (!modal) return
    const res = await fetch(`/api/library/${modal.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
    const updated = await res.json()
    setEntries((prev) => prev.map((e) => (e.id === modal.id ? { ...e, ...updated } : e)))
  }

  async function handleDelete(entry: LibraryEntry) {
    if (!confirm(`Remove "${entry.name}" from your library?`)) return
    await fetch(`/api/library/${entry.id}`, { method: "DELETE" })
    setEntries((prev) => prev.filter((e) => e.id !== entry.id))
  }

  return (
    <div className="p-8 max-w-6xl">
      <h1 className="text-3xl font-bold mb-6">My Library</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        {STATUS_TABS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setStatus(value)}
            className={cn(
              "px-4 py-1.5 rounded-full text-sm font-medium transition-colors",
              status === value
                ? "bg-white text-black"
                : "bg-spotify-card text-spotify-muted hover:text-white"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex gap-2 mb-8">
        {[
          { value: "", label: "All types" },
          { value: "album", label: "Albums" },
          { value: "track", label: "Tracks" },
        ].map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setTypeFilter(value)}
            className={cn(
              "px-3 py-1 rounded-full text-xs font-medium transition-colors",
              typeFilter === value
                ? "bg-spotify-green text-black"
                : "bg-spotify-card text-spotify-muted hover:text-white"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-20 text-spotify-muted">Loading...</div>
      ) : entries.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-spotify-muted mb-2">Nothing here yet.</p>
          <p className="text-spotify-subtle text-sm">Search for music and add it to your library.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {entries.map((entry) => (
            <div key={entry.id} className="group relative bg-spotify-card hover:bg-spotify-card-hover rounded-xl p-4 transition-colors">
              {/* Cover */}
              <div className="relative aspect-square w-full rounded-lg overflow-hidden mb-3 bg-spotify-subtle">
                {entry.imageUrl ? (
                  <Image
                    src={entry.imageUrl}
                    alt={entry.name}
                    fill
                    className="object-cover"
                    sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 20vw"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-spotify-muted text-3xl">♪</div>
                )}

                {/* Hover actions */}
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                  <button
                    onClick={() => setModal(entry)}
                    className="w-9 h-9 bg-white/20 hover:bg-white/30 rounded-full flex items-center justify-center transition-colors"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(entry)}
                    className="w-9 h-9 bg-white/20 hover:bg-red-500/70 rounded-full flex items-center justify-center transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <p className="text-sm font-medium truncate">{entry.name}</p>
              <p className="text-xs text-spotify-muted truncate">{entry.artist}</p>

              <div className="flex items-center justify-between mt-1.5">
                <span className={cn("text-xs font-medium", STATUS_COLORS[entry.status] ?? "text-spotify-muted")}>
                  {STATUS_LABELS[entry.status] ?? entry.status}
                </span>
                {entry.rating && (
                  <span className="flex items-center gap-0.5 text-xs text-spotify-green">
                    <Star className="w-3 h-3 fill-spotify-green" />
                    {entry.rating}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <AddToLibraryModal
          item={{
            spotifyId: modal.spotifyId,
            type: modal.type as "album" | "track",
            name: modal.name,
            artist: modal.artist,
            imageUrl: modal.imageUrl ?? undefined,
            releaseDate: modal.releaseDate ?? undefined,
            spotifyUrl: modal.spotifyUrl ?? undefined,
            durationMs: modal.durationMs ?? undefined,
          }}
          existingEntry={modal}
          onClose={() => setModal(null)}
          onSave={handleUpdate}
        />
      )}
    </div>
  )
}

"use client"

import { useState } from "react"
import { X, Star } from "lucide-react"
import { cn } from "@/lib/utils"

interface AddToLibraryModalProps {
  item: {
    spotifyId: string
    type: "album" | "track"
    name: string
    artist: string
    imageUrl?: string
    releaseDate?: string
    spotifyUrl?: string
    durationMs?: number
  }
  existingEntry?: {
    id: string
    status: string
    rating: number | null
    review: string | null
  } | null
  onClose: () => void
  onSave: (data: {
    status: string
    rating: number | null
    review: string
  }) => Promise<void>
}

const STATUS_OPTIONS = [
  { value: "listening", label: "Listening", color: "bg-spotify-green text-black" },
  { value: "completed", label: "Completed", color: "bg-blue-500 text-white" },
  { value: "plan_to_listen", label: "Plan to Listen", color: "bg-yellow-500 text-black" },
  { value: "dropped", label: "Dropped", color: "bg-red-500 text-white" },
]

export function AddToLibraryModal({ item, existingEntry, onClose, onSave }: AddToLibraryModalProps) {
  const [status, setStatus] = useState(existingEntry?.status ?? "plan_to_listen")
  const [rating, setRating] = useState<number | null>(existingEntry?.rating ?? null)
  const [review, setReview] = useState(existingEntry?.review ?? "")
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    setSaving(true)
    try {
      await onSave({ status, rating, review })
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-spotify-dark rounded-2xl w-full max-w-md shadow-2xl">
        {/* Header */}
        <div className="flex items-start gap-4 p-6 border-b border-white/10">
          {item.imageUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.imageUrl}
              alt={item.name}
              className="w-16 h-16 rounded-lg object-cover flex-shrink-0"
            />
          )}
          <div className="flex-1 min-w-0">
            <p className="text-xs text-spotify-muted uppercase tracking-wider mb-1">
              {item.type === "album" ? "Album" : "Track"}
            </p>
            <h3 className="font-bold text-lg leading-tight truncate">{item.name}</h3>
            <p className="text-spotify-muted text-sm truncate">{item.artist}</p>
          </div>
          <button
            onClick={onClose}
            className="text-spotify-muted hover:text-white transition-colors flex-shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Status */}
          <div>
            <label className="text-sm font-medium text-spotify-muted mb-3 block">Status</label>
            <div className="grid grid-cols-2 gap-2">
              {STATUS_OPTIONS.map(({ value, label, color }) => (
                <button
                  key={value}
                  onClick={() => setStatus(value)}
                  className={cn(
                    "py-2 px-3 rounded-lg text-sm font-medium transition-all border-2",
                    status === value
                      ? `${color} border-transparent`
                      : "border-spotify-subtle text-spotify-muted hover:border-white/30 hover:text-white"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Rating */}
          <div>
            <label className="text-sm font-medium text-spotify-muted mb-3 block">
              Rating {rating ? `(${rating}/10)` : "(optional)"}
            </label>
            <div className="flex gap-1">
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <button
                  key={n}
                  onClick={() => setRating(rating === n ? null : n)}
                  className="flex-1 group"
                >
                  <Star
                    className={cn(
                      "w-full h-auto transition-colors",
                      n <= (rating ?? 0)
                        ? "fill-spotify-green text-spotify-green"
                        : "text-spotify-subtle group-hover:text-spotify-muted"
                    )}
                  />
                </button>
              ))}
            </div>
          </div>

          {/* Review */}
          <div>
            <label className="text-sm font-medium text-spotify-muted mb-2 block">
              Notes <span className="text-spotify-subtle">(optional)</span>
            </label>
            <textarea
              value={review}
              onChange={(e) => setReview(e.target.value)}
              rows={3}
              placeholder="Your thoughts..."
              className="w-full bg-spotify-card rounded-lg px-3 py-2 text-sm text-white placeholder:text-spotify-subtle resize-none outline-none focus:ring-2 focus:ring-spotify-green"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3 p-6 pt-0">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 rounded-full border border-spotify-subtle text-spotify-muted hover:text-white hover:border-white/30 text-sm font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 py-2.5 rounded-full bg-spotify-green hover:bg-spotify-green-hover text-black font-bold text-sm transition-colors disabled:opacity-50"
          >
            {saving ? "Saving..." : existingEntry ? "Update" : "Add to Library"}
          </button>
        </div>
      </div>
    </div>
  )
}

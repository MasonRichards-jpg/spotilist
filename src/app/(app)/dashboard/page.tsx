import { auth } from "@/auth"
import { prisma } from "@/lib/prisma"
import { STATUS_LABELS } from "@/lib/utils"
import Image from "next/image"
import Link from "next/link"

async function getStats(userId: string) {
  const [total, byStatus] = await Promise.all([
    prisma.libraryEntry.count({ where: { userId } }),
    prisma.libraryEntry.groupBy({
      by: ["status"],
      where: { userId },
      _count: true,
    }),
  ])

  const statusMap = Object.fromEntries(byStatus.map((s) => [s.status, s._count]))
  return { total, statusMap }
}

async function getRecentEntries(userId: string) {
  return prisma.libraryEntry.findMany({
    where: { userId },
    orderBy: { updatedAt: "desc" },
    take: 8,
  })
}

export default async function DashboardPage() {
  const session = await auth()
  const userId = session!.user.id

  const [stats, recentEntries] = await Promise.all([
    getStats(userId),
    getRecentEntries(userId),
  ])

  const statCards = [
    { label: "Total", value: stats.total, color: "text-white" },
    { label: STATUS_LABELS.completed, value: stats.statusMap.completed ?? 0, color: "text-blue-400" },
    { label: STATUS_LABELS.listening, value: stats.statusMap.listening ?? 0, color: "text-spotify-green" },
    { label: STATUS_LABELS.plan_to_listen, value: stats.statusMap.plan_to_listen ?? 0, color: "text-yellow-400" },
    { label: STATUS_LABELS.dropped, value: stats.statusMap.dropped ?? 0, color: "text-red-400" },
  ]

  return (
    <div className="p-8 max-w-6xl">
      <h1 className="text-3xl font-bold mb-1">
        Welcome back, {session!.user.name?.split(" ")[0] ?? "Listener"}
      </h1>
      <p className="text-spotify-muted mb-8">Here&apos;s what&apos;s going on with your music library.</p>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-10">
        {statCards.map(({ label, value, color }) => (
          <div key={label} className="bg-spotify-card rounded-xl p-5">
            <p className={`text-3xl font-bold ${color}`}>{value}</p>
            <p className="text-spotify-muted text-sm mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Recent library */}
      <div className="mb-10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold">Recently Added</h2>
          <Link href="/library" className="text-sm text-spotify-muted hover:text-white transition-colors">
            See all
          </Link>
        </div>

        {recentEntries.length === 0 ? (
          <div className="bg-spotify-card rounded-xl p-10 text-center">
            <p className="text-spotify-muted mb-4">Your library is empty.</p>
            <Link
              href="/search"
              className="inline-block bg-spotify-green hover:bg-spotify-green-hover text-black font-bold px-6 py-2 rounded-full text-sm transition-colors"
            >
              Search for music
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8 gap-4">
            {recentEntries.map((entry) => (
              <Link
                key={entry.id}
                href="/library"
                className="group bg-spotify-card hover:bg-spotify-card-hover rounded-xl p-3 transition-colors"
              >
                <div className="aspect-square w-full rounded-lg overflow-hidden mb-3 bg-spotify-subtle">
                  {entry.imageUrl ? (
                    <Image
                      src={entry.imageUrl}
                      alt={entry.name}
                      width={200}
                      height={200}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-spotify-subtle">
                      ♪
                    </div>
                  )}
                </div>
                <p className="text-sm font-medium truncate">{entry.name}</p>
                <p className="text-xs text-spotify-muted truncate">{entry.artist}</p>
                {entry.rating && (
                  <p className="text-xs text-spotify-green mt-1">★ {entry.rating}/10</p>
                )}
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div className="flex gap-4">
        <Link
          href="/search"
          className="bg-spotify-green hover:bg-spotify-green-hover text-black font-bold px-6 py-3 rounded-full text-sm transition-colors"
        >
          Search Music
        </Link>
        <Link
          href="/library"
          className="bg-spotify-card hover:bg-spotify-card-hover text-white font-bold px-6 py-3 rounded-full text-sm transition-colors"
        >
          My Library
        </Link>
      </div>
    </div>
  )
}

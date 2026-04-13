import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/auth"
import { getValidAccessToken, spotifySearch } from "@/lib/spotify"

export async function GET(req: NextRequest) {
  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { searchParams } = req.nextUrl
  const query = searchParams.get("q")
  const types = searchParams.get("types")?.split(",") ?? ["album", "track"]

  if (!query) {
    return NextResponse.json({ error: "Missing query" }, { status: 400 })
  }

  const token = await getValidAccessToken(session.user.id)
  if (!token) {
    return NextResponse.json({ error: "No Spotify token" }, { status: 401 })
  }

  try {
    const results = await spotifySearch(token, query, types)
    return NextResponse.json(results)
  } catch (err) {
    console.error("Search error:", err)
    return NextResponse.json({ error: "Search failed" }, { status: 500 })
  }
}

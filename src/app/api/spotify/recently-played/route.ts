import { NextResponse } from "next/server"
import { auth } from "@/auth"
import { getValidAccessToken, getRecentlyPlayed } from "@/lib/spotify"

export async function GET() {
  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const token = await getValidAccessToken(session.user.id)
  if (!token) {
    return NextResponse.json({ error: "No Spotify token" }, { status: 401 })
  }

  try {
    const data = await getRecentlyPlayed(token, 50)
    return NextResponse.json(data)
  } catch (err) {
    console.error("Recently played error:", err)
    return NextResponse.json({ error: "Failed to fetch" }, { status: 500 })
  }
}

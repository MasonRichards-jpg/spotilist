import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/auth"
import { prisma } from "@/lib/prisma"

export async function GET(req: NextRequest) {
  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const { searchParams } = req.nextUrl
  const status = searchParams.get("status")
  const type = searchParams.get("type")

  const entries = await prisma.libraryEntry.findMany({
    where: {
      userId: session.user.id,
      ...(status ? { status } : {}),
      ...(type ? { type } : {}),
    },
    orderBy: { updatedAt: "desc" },
  })

  return NextResponse.json(entries)
}

export async function POST(req: NextRequest) {
  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const body = await req.json()
  const { spotifyId, type, name, artist, imageUrl, releaseDate, spotifyUrl, durationMs, status, rating, review } = body

  if (!spotifyId || !type || !name || !artist) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 })
  }

  const entry = await prisma.libraryEntry.upsert({
    where: { userId_spotifyId: { userId: session.user.id, spotifyId } },
    create: {
      userId: session.user.id,
      spotifyId,
      type,
      name,
      artist,
      imageUrl,
      releaseDate,
      spotifyUrl,
      durationMs,
      status: status ?? "plan_to_listen",
      rating,
      review,
    },
    update: {
      status: status ?? "plan_to_listen",
      rating,
      review,
      imageUrl,
    },
  })

  return NextResponse.json(entry)
}

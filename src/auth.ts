import NextAuth from "next-auth"
import Spotify from "next-auth/providers/spotify"
import { PrismaAdapter } from "@auth/prisma-adapter"
import { prisma } from "@/lib/prisma"

const SPOTIFY_SCOPES = [
  "user-read-email",
  "user-read-recently-played",
  "user-top-read",
  "user-library-read",
  "user-read-playback-state",
].join(" ")

const BASE_URL = process.env.NEXTAUTH_URL ?? process.env.AUTH_URL ?? "http://127.0.0.1:3737"

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  adapter: PrismaAdapter(prisma),
  providers: [
    Spotify({
      clientId: process.env.SPOTIFY_CLIENT_ID!,
      clientSecret: process.env.SPOTIFY_CLIENT_SECRET!,
      authorization: `https://accounts.spotify.com/authorize?scope=${encodeURIComponent(SPOTIFY_SCOPES)}&redirect_uri=${encodeURIComponent(`${BASE_URL}/api/auth/callback/spotify`)}`,
    }),
  ],
  callbacks: {
    session({ session, user }) {
      session.user.id = user.id
      return session
    },
  },
  pages: {
    signIn: "/login",
  },
})

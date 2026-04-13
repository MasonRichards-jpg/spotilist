"use client"

import { signIn } from "next-auth/react"

interface Props {
  className?: string
  children?: React.ReactNode
}

export function SpotifySignInButton({ className, children }: Props) {
  return (
    <button
      onClick={() => signIn("spotify", { callbackUrl: "/dashboard" })}
      className={className}
    >
      {children}
    </button>
  )
}

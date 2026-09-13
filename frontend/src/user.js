import { createContext, useContext } from 'react'

/**
 * The signed-in member, as returned by /api/auth/check.
 *
 * Only used for presentation - hiding owner-only controls from members who
 * cannot use them. Every check is enforced again by the server.
 */
export const UserContext = createContext(null)

export function useUser() {
  return useContext(UserContext)
}

export function useIsOwner() {
  return useUser()?.role === 'owner'
}

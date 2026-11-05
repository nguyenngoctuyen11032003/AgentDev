// Pure helpers for the Connections screen (no Vue), covered by connectionsLogic.test.js.

// Only non-CLI (Google sign-in) connections need a live model listing; the API field is authType.
export const needsLiveModels = (conn) => conn.authType !== 'cli'

// Connections of a vendor that can actually run: a signed-out account is not "ready".
export const readyCount = (connections, accounts, vendorId) =>
  connections.filter((conn) => conn.vendor === vendorId && accounts[conn.id]?.loggedIn !== false).length

// Which toast to show after a delete. Honors what the server really did (cliLoggedOut).
// The server keeps the CLI login when another connection of the same vendor shares it (sharedWithOther):
// that is deliberate, not a failure.
export const sharesCliLogin = (connections, conn) =>
  conn.authType === 'cli' && connections.some((c) => c.id !== conn.id && c.authType === 'cli' && c.vendor === conn.vendor)

export function logoutToast(result, signOutRequested, sharedWithOther = false) {
  if (signOutRequested) {
    if (result?.cliLoggedOut) return 'logged_out_cli'
    return sharedWithOther ? 'logout_cli_kept' : 'logout_cli_failed'
  }
  return 'logged_out'
}

// Pure helpers for the Connections screen (no Vue), covered by connectionsLogic.test.js.

// Only non-CLI (Google sign-in) connections need a live model listing; the API field is authType.
export const needsLiveModels = (conn) => conn.authType !== 'cli'

// Connections of a vendor that can actually run: a signed-out account is not "ready".
export const readyCount = (connections, accounts, vendorId) =>
  connections.filter((conn) => conn.vendor === vendorId && accounts[conn.id]?.loggedIn !== false).length

// Which toast to show after a delete. Honors what the server really did (cliLoggedOut).
export function logoutToast(result, signOutRequested) {
  if (signOutRequested) return result?.cliLoggedOut ? 'logged_out_cli' : 'logout_cli_failed'
  return 'logged_out'
}

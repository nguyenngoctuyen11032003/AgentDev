// Keeps only the newest of overlapping async calls: older results are reported as stale so a slow
// response can never overwrite state that belongs to a newer request.
export function createLatest() {
  let seq = 0
  return {
    // Returns a ticket; `isCurrent(ticket)` is false once a newer ticket was issued.
    begin: () => ++seq,
    isCurrent: (ticket) => ticket === seq,
    // Invalidates every pending ticket (e.g. on unmount or dialog close).
    cancel: () => {
      seq += 1
    }
  }
}

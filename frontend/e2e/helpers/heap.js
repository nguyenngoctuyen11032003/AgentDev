// Optional: JS heap measurement through CDP (Chromium only).
// const heap = await measureHeap(page)  -> { usedMB, totalMB } after a forced GC.
export async function measureHeap(page, { gc = true } = {}) {
  const client = await page.context().newCDPSession(page)
  try {
    if (gc) await client.send('HeapProfiler.collectGarbage')
    const { result } = await client.send('Runtime.evaluate', {
      expression: 'JSON.stringify({u: performance.memory && performance.memory.usedJSHeapSize, t: performance.memory && performance.memory.totalJSHeapSize})',
      returnByValue: true,
    })
    const { u, t } = JSON.parse(result.value)
    const mb = (n) => (n == null ? null : Math.round((n / 1048576) * 10) / 10)
    return { usedMB: mb(u), totalMB: mb(t) }
  } finally {
    await client.detach().catch(() => {})
  }
}

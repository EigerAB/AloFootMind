export interface SseStreamOptions {
  onEvent: (data: Record<string, unknown>) => void
  onDone: (data: Record<string, unknown>) => void
  onError: (err: string) => void
  onToken?: (token: string) => void
}

export function useSseStream() {
  let abortController: AbortController | null = null

  async function start(url: string, options: SseStreamOptions): Promise<void> {
    abortController = new AbortController()

    try {
      const res = await fetch(url, {
        method: 'GET',
        signal: abortController.signal,
        headers: { Accept: 'text/event-stream' },
      })
      await _readStream(res, options)
    } catch (err: unknown) {
      if ((err as Error)?.name !== 'AbortError') {
        options.onError(String(err))
      }
    }
  }

  async function post(
    url: string,
    body: Record<string, unknown>,
    options: SseStreamOptions
  ): Promise<void> {
    abortController = new AbortController()

    try {
      const res = await fetch(url, {
        method: 'POST',
        signal: abortController.signal,
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(body),
      })
      await _readStream(res, options)
    } catch (err: unknown) {
      if ((err as Error)?.name !== 'AbortError') {
        options.onError(String(err))
      }
    }
  }

  async function _readStream(res: Response, options: SseStreamOptions): Promise<void> {
    if (!res.body) {
      options.onError('No response body')
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() ?? ''

      for (const raw of events) {
        if (!raw.trim()) continue
        const lines = raw.split('\n')
        let eventType = 'message'
        let dataLine = ''

        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim()
          if (line.startsWith('data: ')) dataLine = line.slice(6).trim()
        }

        if (!dataLine) continue

        try {
          const parsed = JSON.parse(dataLine)
          if (eventType === 'done') {
            options.onDone(parsed)
            return
          } else if (eventType === 'error') {
            options.onError(parsed.error ?? 'Unknown error')
            return
          } else {
            if (parsed.token && options.onToken) {
              options.onToken(parsed.token as string)
            } else {
              options.onEvent(parsed)
            }
          }
        } catch {
          // malformed SSE chunk — skip
        }
      }
    }
  }

  function stop(): void {
    abortController?.abort()
    abortController = null
  }

  return { start, post, stop }
}

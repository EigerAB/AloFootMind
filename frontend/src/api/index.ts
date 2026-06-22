const BASE_URL = ''

interface SseStreamOptions {
  onToken?: (token: string) => void
  onStep?: (step: Record<string, unknown>) => void
  onDone: (data: Record<string, unknown>) => void
  onError: (err: string) => void
}

const TRIAL_EXPIRED_MSG = 'Trial account has expired'

function _clearAuthAndRedirect() {
  sessionStorage.removeItem('access_token')
  sessionStorage.removeItem('refresh_token')
  sessionStorage.removeItem('user')
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
  window.location.href = '/login'
}

function getAuthHeader(): Record<string, string> {
  const token = sessionStorage.getItem('access_token') || localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

let isRefreshing = false
let refreshPromise: Promise<string | null> | null = null

async function doRefresh(): Promise<string | null> {
  if (isRefreshing && refreshPromise) {
    return refreshPromise
  }
  isRefreshing = true
  refreshPromise = (async () => {
    const rt = sessionStorage.getItem('refresh_token') || localStorage.getItem('refresh_token')
    if (!rt) return null
    try {
      const res = await fetch(`${BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      })
      if (res.status === 403) {
        const err = await res.json().catch(() => ({ detail: '' }))
        if (err.detail?.includes(TRIAL_EXPIRED_MSG)) {
          _clearAuthAndRedirect()
          return null
        }
      }
      if (!res.ok) return null
      const data = await res.json()
      const temp = data.user?.role === 'guest'
      const store = temp ? sessionStorage : localStorage
      store.setItem('access_token', data.access_token)
      if (data.refresh_token) {
        store.setItem('refresh_token', data.refresh_token)
      }
      if (data.user) {
        store.setItem('user', JSON.stringify(data.user))
      }
      return data.access_token as string
    } catch {
      return null
    } finally {
      isRefreshing = false
      refreshPromise = null
    }
  })()
  return refreshPromise
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`
  const makeRequest = (token?: string) =>
    fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : getAuthHeader()),
        ...(options?.headers ?? {}),
      },
      ...options,
    })

  let res = await makeRequest()

  // Try refresh on 401 if we have a refresh token
  if (res.status === 401) {
    const rtBefore = sessionStorage.getItem('refresh_token') || localStorage.getItem('refresh_token')
    const newToken = await doRefresh()
    if (newToken) {
      res = await makeRequest(newToken)
    } else {
      // Refresh failed — clear auth state only if no other tab updated the token
      const rtAfter = sessionStorage.getItem('refresh_token') || localStorage.getItem('refresh_token')
      if (rtAfter === rtBefore) {
        sessionStorage.removeItem('access_token')
        sessionStorage.removeItem('refresh_token')
        sessionStorage.removeItem('user')
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        localStorage.removeItem('user')
      }
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    if (res.status === 403 && err.detail?.includes(TRIAL_EXPIRED_MSG)) {
      _clearAuthAndRedirect()
      throw new Error(err.detail)
    }
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  getCompetitions: () => request<Competition[]>('/api/competitions'),
  getTeams: (q?: string) =>
    request<Team[]>(`/api/teams${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  getTeamsHierarchy: () => request<CompetitionWithTeams[]>('/api/teams/hierarchy'),

  getMatches: (params?: {
    competition_id?: number
    season_id?: number
    team_id?: number
    limit?: number
    offset?: number
  }) => {
    return request<{ items: Match[]; total: number }>('/api/matches', {
      method: 'POST',
      body: JSON.stringify({
        competition_id: params?.competition_id ?? null,
        season_id: params?.season_id ?? null,
        team_id: params?.team_id ?? null,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      }),
    })
  },

  getMatch: (id: number) => request<MatchDetail>(`/api/matches/${id}`),

  getMatchReport: (id: number, language = 'en') =>
    request<{ match_id: number; report_markdown: string; created_at: string }>(
      `/api/matches/${id}/report?language=${language}`
    ),

  triggerAnalysis: (matchId: number, language = 'en') =>
    request<{ match_id: number; task_id: string | null; status: string }>(
      `/api/matches/${matchId}/analyze`,
      { method: 'POST', body: JSON.stringify({ language }) }
    ),

  triggerPreMatch: (homeTeamId: number, awayTeamId: number, language = 'en') =>
    request<{ task_id: string; status: string }>('/api/pre-match', {
      method: 'POST',
      body: JSON.stringify({ home_team_id: homeTeamId, away_team_id: awayTeamId, language }),
    }),

  getTaskStatus: (taskId: string) =>
    request<{ task_id: string; status: string; has_result: boolean }>(
      `/api/tasks/${taskId}/status`
    ),

  getTaskResult: (taskId: string) =>
    request<{ task_id: string; result: string }>(
      `/api/tasks/${taskId}/result`
    ),

  getPreMatchReports: () =>
    request<PreMatchReport[]>('/api/pre-match/reports'),

  deletePreMatchReport: (id: number) =>
    request<{ message: string }>(`/api/pre-match/reports/${id}`, { method: 'DELETE' }),

  clearPreMatchReports: () =>
    request<{ message: string }>('/api/pre-match/reports', { method: 'DELETE' }),

  // Chat sessions
  getChatSessions: () =>
    request<ChatSession[]>('/api/chat/sessions'),

  createChatSession: (name?: string, initialMessage?: string) =>
    request<{ id: number; name: string }>('/api/chat/sessions', {
      method: 'POST',
      body: JSON.stringify({ name: name ?? null, initial_message: initialMessage ?? null }),
    }),

  renameChatSession: (id: number, name: string) =>
    request<{ message: string }>(`/api/chat/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  cancelChatSession: (id: number, messages?: any[]) =>
    request<{ ok: boolean }>(`/api/chat/sessions/${id}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ messages: messages ?? null }),
    }),

  deleteChatSession: (id: number) =>
    request<{ message: string }>(`/api/chat/sessions/${id}`, { method: 'DELETE' }),

  loadChatSession: (id: number, offset?: number, limit?: number) => {
    const params = new URLSearchParams()
    if (offset !== undefined) params.set('offset', String(offset))
    if (limit !== undefined) params.set('limit', String(limit))
    const qs = params.toString()
    return request<{ id: number; name: string; messages: ChatMessage[]; total: number; qa_meta: QaMeta }>(
      `/api/chat/sessions/${id}${qs ? `?${qs}` : ''}`
    ).catch(() => null)
  },

  // Chat plan + stream (new two-step flow)
  planChat: (body: {
    query: string
    session_id?: number | null
    conversation_history?: { role: string; content: string }[]
    qa_meta?: QaMeta
  }) =>
    request<PlanResponse>('/api/chat/plan', { method: 'POST', body: JSON.stringify(body) }),

  planChatStream: (
    body: {
      query: string
      session_id?: number | null
      conversation_history?: { role: string; content: string }[]
      qa_meta?: QaMeta
    },
    options: SseStreamOptions
  ) => {
    const abortController = new AbortController()
    const url = `${BASE_URL}/api/chat/plan/stream`
    const promise = (async () => {
      try {
        const res = await fetch(url, {
          method: 'POST',
          signal: abortController.signal,
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            ...getAuthHeader(),
          },
          body: JSON.stringify(body),
        })
        if (!res.ok) {
          const text = await res.text().catch(() => 'Request failed')
          options.onError(text || `HTTP ${res.status}`)
          return
        }
        const reader = res.body?.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        if (!reader) { options.onError('No response body'); return }
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
              if (eventType === 'step' && options.onStep) {
                options.onStep(parsed)
              } else if (eventType === 'done') {
                options.onDone(parsed)
              } else if (eventType === 'error') {
                options.onError(parsed.error ?? 'Unknown error')
              }
            } catch { /* ignore parse errors */ }
          }
        }
      } catch (err: unknown) {
        if ((err as Error)?.name !== 'AbortError') {
          options.onError(String(err))
        }
      }
    })()
    return { promise, abort: () => abortController.abort() }
  },

  streamChat: (
    body: {
      query: string
      session_id?: number | null
      conversation_history?: { role: string; content: string }[]
      qa_meta?: QaMeta
      rag_context?: RagHit[]
      step_log?: StepEntry[]
      route?: string
    },
    options: SseStreamOptions
  ) => {
    const abortController = new AbortController()
    const url = `${BASE_URL}/api/chat/stream`
    const promise = (async () => {
      try {
        const res = await fetch(url, {
          method: 'POST',
          signal: abortController.signal,
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            ...getAuthHeader(),
          },
          body: JSON.stringify(body),
        })
        if (!res.ok) {
          const text = await res.text().catch(() => 'Request failed')
          options.onError(text || `HTTP ${res.status}`)
          return
        }
        // Read SSE stream
        const reader = res.body?.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        if (!reader) {
          options.onError('No response body')
          return
        }
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6)
              try {
                const parsed = JSON.parse(data)
                if (parsed.token) options.onToken(parsed.token)
                if (parsed.sources || parsed.qa_meta || parsed.session_id !== undefined) {
                  options.onDone(parsed)
                }
              } catch {
                // ignore parse errors
              }
            }
          }
        }
      } catch (err: unknown) {
        if ((err as Error)?.name !== 'AbortError') {
          options.onError(String(err))
        }
      }
    })()
    return { promise, abort: () => abortController.abort() }
  },

  // Auth
  register: (body: { email: string; password: string; nickname: string }) =>
    request<{ message: string }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  verifyEmail: (body: { email: string; code: string }) =>
    request<{ message: string }>('/api/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  login: (body: { email: string; password: string }) =>
    request<{ access_token: string; refresh_token: string; user: User }>(
      '/api/auth/login',
      { method: 'POST', body: JSON.stringify(body) }
    ),

  refresh: (token: string) =>
    request<{ access_token: string; refresh_token: string; user: User }>('/api/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: token }),
    }),

  logout: (refreshToken: string) =>
    request<{ message: string }>('/api/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),

  forgotPassword: (body: { email: string }) =>
    request<{ message: string }>('/api/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  resetPassword: (body: { email: string; code: string; new_password: string }) =>
    request<{ message: string }>('/api/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  me: () => request<User>('/api/auth/me'),

  guestLogin: () =>
    request<{ access_token: string; refresh_token: string; user: User }>('/api/auth/guest-login', {
      method: 'POST',
    }),
}

export interface User {
  id: number
  email: string
  nickname: string
  role: string
}

export interface Competition {
  competition_id: number
  competition_name: string
  country_name: string
  season_id: number
  season_name: string
}

export interface Team {
  team_id: number
  team_name: string
}

export interface CompetitionWithTeams {
  competition_id: number
  competition_name: string
  teams: Team[]
}

export interface PreMatchReport {
  id: number
  home_team_id: number
  away_team_id: number
  home_team_name: string
  away_team_name: string
  report_markdown: string
  created_at: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: { text: string; collection: string; score?: number }[]
  thinking?: {
    steps: StepEntry[]
    rag_context: RagHit[]
  }
}

export interface QaMeta {
  football_intent_count: number
  generic_turn_count: number
}

export interface RagHit {
  text: string
  collection: string
  score: number
}

export interface PlanResponse {
  step_log: StepEntry[]
  rag_context: RagHit[]
  analysis_result: {
    _route: string
    rewritten_query: string
    query_levels: string[]
    rag_plan: any[]
    qa_meta: QaMeta
  }
  session_id: number | null
}

export interface StepEntry {
  node_name: string
  status: 'started' | 'completed' | 'failed'
  summary: string
  data?: any
}

export interface ChatSession {
  id: number
  name: string
  updated_at: string
  preview: string
}

export interface Match {
  match_id: number
  match_date: string
  home_score: number
  away_score: number
  match_week: number | null
  home_formation: number | null
  away_formation: number | null
  home_team_name: string
  away_team_name: string
  competition_name: string
  season_name: string
  has_report?: boolean
}

export interface MatchDetail extends Match {
  home_team_id: number
  away_team_id: number
  stadium_name: string | null
  home_manager: string | null
  away_manager: string | null
  home_shots: number
  away_shots: number
  home_shots_on_target: number
  away_shots_on_target: number
  home_passes: number
  away_passes: number
  home_fouls: number
  away_fouls: number
  key_events: KeyEvent[]
  lineups: LineupPlayer[]
}

export interface KeyEvent {
  type: string
  team_id: number
  player: string
  minute: number
  period: number
}

export interface LineupPlayer {
  player_id: number
  player_name: string
  team_id: number
  position_name: string | null
  jersey_number: number | null
}

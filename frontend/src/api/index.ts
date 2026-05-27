const BASE_URL = ''

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  getCompetitions: () => request<Competition[]>('/api/competitions'),
  getTeams: (q?: string) =>
    request<Team[]>(`/api/teams${q ? `?q=${encodeURIComponent(q)}` : ''}`),

  getMatches: (params?: {
    competition_id?: number
    season_id?: number
    team_id?: number
    limit?: number
    offset?: number
  }) => {
    const qs = new URLSearchParams()
    if (params?.competition_id) qs.set('competition_id', String(params.competition_id))
    if (params?.season_id) qs.set('season_id', String(params.season_id))
    if (params?.team_id) qs.set('team_id', String(params.team_id))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.offset) qs.set('offset', String(params.offset))
    return request<Match[]>(`/api/matches?${qs}`)
  },

  getMatch: (id: number) => request<MatchDetail>(`/api/matches/${id}`),

  getMatchReport: (id: number) =>
    request<{ match_id: number; report_markdown: string; created_at: string }>(
      `/api/matches/${id}/report`
    ),

  triggerAnalysis: (matchId: number) =>
    request<{ match_id: number; task_id: string | null; status: string }>(
      `/api/matches/${matchId}/analyze`,
      { method: 'POST' }
    ),

  triggerPreMatch: (homeTeamId: number, awayTeamId: number) =>
    request<{ task_id: string; status: string }>('/api/pre-match', {
      method: 'POST',
      body: JSON.stringify({ home_team_id: homeTeamId, away_team_id: awayTeamId }),
    }),

  getTaskStatus: (taskId: string) =>
    request<{ task_id: string; status: string; has_result: boolean }>(
      `/api/tasks/${taskId}/status`
    ),

  getTaskResult: (taskId: string) =>
    request<{ task_id: string; result: string }>(
      `/api/tasks/${taskId}/result`
    ),
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

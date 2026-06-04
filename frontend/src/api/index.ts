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

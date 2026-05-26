// API 客户端 — fetch wrapper
const BASE = '/api';

async function req<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  // documents
  listDocs: () => req<DocumentItem[]>('/documents'),
  getDoc: (id: string) => req<DocumentItem>(`/documents/${id}`),
  deleteDoc: (id: string) => req(`/documents/${id}`, { method: 'DELETE' }),
  upload: async (file: File): Promise<DocumentItem> => {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(BASE + '/documents', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },
  preview: (id: string) => req<Preview>(`/documents/${id}/preview?_t=${Date.now()}`),
  downloadUrl: (id: string) => `${BASE}/documents/${id}/download`,

  // proofread
  proofread: (id: string) => req<{ new: number; by_layer: Record<string, number>; state: State }>(
    `/documents/${id}/proofread`, { method: 'POST' }),

  // errors
  listErrors: (id: string) => req<Finding[]>(`/documents/${id}/errors`),
  acceptError: (eid: string, body: any = {}) =>
    req<{ msg: string; state: State; l5_warnings: number }>(`/errors/${eid}/accept`,
      { method: 'POST', body: JSON.stringify(body) }),
  rejectError: (eid: string, reason: string) =>
    req<{ msg: string; state: State }>(`/errors/${eid}/reject`,
      { method: 'POST', body: JSON.stringify({ reason }) }),
  undoError: (eid: string) =>
    req<{ msg: string; state: State }>(`/errors/${eid}/undo`, { method: 'POST' }),
  batchAccept: (id: string, filter: any) =>
    req<{ applied: number; state: State }>(`/documents/${id}/batch_accept`,
      { method: 'POST', body: JSON.stringify(filter) }),
  batchReject: (id: string, filter: any) =>
    req<{ rejected: number; state: State }>(`/documents/${id}/batch_reject`,
      { method: 'POST', body: JSON.stringify(filter) }),

  // direct change / alternatives
  directChange: (id: string, body: any) =>
    req<{ msg: string; finding_id: string; state: State }>(`/documents/${id}/direct_change`,
      { method: 'POST', body: JSON.stringify(body) }),
  suggestAlts: (id: string, body: any) =>
    req<{ alternatives: Alternative[] }>(`/documents/${id}/suggest_alternatives`,
      { method: 'POST', body: JSON.stringify(body) }),

  // chat
  getMessages: (id: string) => req<ChatMsg[]>(`/documents/${id}/messages`),
  sendChat: (id: string, message: string) =>
    req<{ reply: string; new_edits: number; new_candidates: any[]; state: State }>(
      `/documents/${id}/chat`, { method: 'POST', body: JSON.stringify({ message }) }),

  // rules
  listRules: () => req<Rule[]>('/rules'),
  disableRule: (rid: string) => req(`/rules/${rid}`, { method: 'DELETE' }),
  listCandidates: () => req<RuleCandidate[]>('/rule_candidates'),
  approveCandidate: (cid: string) => req(`/rule_candidates/${cid}/approve`, { method: 'POST' }),
  archiveCandidate: (cid: string) => req(`/rule_candidates/${cid}/archive`, { method: 'POST' }),

  // skills
  listSkills: () => req<Skill[]>('/skills'),
  toggleSkill: (sid: string, enabled: boolean) =>
    req<{ ok: boolean }>(`/skills/${sid}`, { method: 'PATCH', body: JSON.stringify({ enabled }) }),

  // user-defined prompt skills
  createUserSkill: (body: { name: string; description: string; prompt: string; phase: number }) =>
    req<UserSkill>('/user_skills', { method: 'POST', body: JSON.stringify(body) }),
  updateUserSkill: (uid: string, body: Partial<UserSkill>) =>
    req<UserSkill>(`/user_skills/${uid}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteUserSkill: (uid: string) =>
    req<{ ok: boolean }>(`/user_skills/${uid}`, { method: 'DELETE' }),
  getUserSkill: (uid: string) => req<UserSkill>(`/user_skills/${uid}`),

  // settings (LLM 配置)
  getSettings: () => req<LLMSettings>('/settings'),
  updateSettings: (body: Partial<LLMSettingsWrite>) =>
    req<LLMSettings>('/settings', { method: 'PUT', body: JSON.stringify(body) }),
  testSettings: (body: Partial<LLMSettingsWrite>) =>
    req<{ ok: boolean; model?: string; reply?: string; error?: string }>(
      '/settings/test', { method: 'POST', body: JSON.stringify(body) }),

  // export
  export: (id: string) => req<{ download_url: string }>(`/documents/${id}/export`, { method: 'POST' }),
};

// ---------- 类型 ----------
export interface DocumentItem {
  id: string;
  filename: string;
  paragraph_count: number;
  word_count: number;
  created_at: string;
}

export interface State {
  pending: number;
  accepted: number;
  rejected: number;
  failed: number;
  total: number;
}

export interface Finding {
  id: string;
  doc_id: string;
  layer: string;
  type: string;
  confidence: string;
  paragraph_idx: number;
  char_start: number;
  char_end: number;
  original: string;
  suggestion: string;
  explanation: string;
  status: string;
  source: string;
  user_feedback?: string;
  final_text?: string;
  created_at: string;
}

export interface Preview {
  paragraphs: Array<{
    idx: number;
    style: string;
    runs: Array<{ type: 'text' | 'ins' | 'del'; text: string }>;
  }>;
}

export interface ChatMsg {
  id: string;
  doc_id: string;
  role: string;
  content: string;
  metadata: Record<string, any>;
  created_at: string;
}

export interface Rule {
  id: string;
  summary: string;
  category: string;
  examples: string[];
  hit_count: number;
  enabled: boolean;
  created_at: string;
}

export interface RuleCandidate {
  id: string;
  summary: string;
  category: string;
  source: string;
  evidence: string[];
  status: string;
  created_at: string;
}

export interface Skill {
  id: string;
  name: string;
  scope: string;
  layers: string[];
  description: string;
  enabled: boolean;
  phase: number;
  runnable: boolean;
}

export interface LLMSettings {
  LLM_PROVIDER: 'openai' | 'anthropic';
  OPENAI_BASE_URL: string;
  OPENAI_API_KEY_masked: string;
  LLM_MODEL: string;
}

export interface LLMSettingsWrite {
  LLM_PROVIDER?: 'openai' | 'anthropic';
  OPENAI_BASE_URL: string;
  OPENAI_API_KEY?: string;
  LLM_MODEL: string;
}

export interface UserSkill {
  id: string;
  name: string;
  description: string;
  prompt: string;
  phase: number;
  enabled: number | boolean;
  created_at: string;
}

export interface Alternative {
  text: string;
  label: string;
  reason: string;
}

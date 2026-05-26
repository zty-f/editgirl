import { useEffect, useState } from 'react'
import { X, CheckCircle2, Plus, Trash2, Pencil } from 'lucide-react'
import { api, type Skill } from '../lib/api'

interface Props { open: boolean; onClose: () => void }

interface FormState {
  id?: string  // 编辑时
  name: string
  description: string
  prompt: string
  phase: number
}

const DEFAULT_FORM: FormState = {
  name: '', description: '', phase: 50,
  prompt: `你是 XX 专题校对员,只检查以下问题:
1. ...(描述你想抓的错)
2. ...

报错时只标真正要换的最小片段。对话/方言/文学化表达不报。`,
}

export default function SkillsModal({ open, onClose }: Props) {
  const [skills, setSkills] = useState<Skill[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [editing, setEditing] = useState<FormState | null>(null)

  const refresh = () => api.listSkills().then(setSkills)
  useEffect(() => { if (open) refresh() }, [open])

  const toggle = async (s: Skill) => {
    if (!s.runnable) return
    setBusy(s.id)
    try {
      await api.toggleSkill(s.id, !s.enabled)
      await refresh()
    } finally { setBusy(null) }
  }

  const onEdit = async (s: Skill) => {
    if (!s.id.startsWith('user.')) return
    const uid = s.id.slice(5)
    const detail = await api.getUserSkill(uid)
    setEditing({ id: uid, name: detail.name, description: detail.description, prompt: detail.prompt, phase: detail.phase })
  }

  const onDelete = async (s: Skill) => {
    if (!s.id.startsWith('user.')) return
    if (!confirm(`删除「${s.name}」?`)) return
    await api.deleteUserSkill(s.id.slice(5))
    await refresh()
  }

  if (!open) return null
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-6" onClick={onClose}>
      <div className="bg-white rounded-2xl max-w-3xl w-full max-h-[85vh] overflow-hidden shadow-2xl flex flex-col"
           onClick={e => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-gradient-to-r from-brand-50 to-purple-50">
          <div>
            <h3 className="text-lg font-semibold bg-gradient-to-r from-brand-600 to-purple-600 bg-clip-text text-transparent">🧩 能力中心(Skills)</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              ✓ = 主校对调用 · ○ = 声明展示。开关实时生效,下次校对自动应用。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn btn-primary text-xs" onClick={() => setEditing(DEFAULT_FORM)}>
              <Plus className="w-3.5 h-3.5" /> 新建 Skill
            </button>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-700"><X className="w-5 h-5" /></button>
          </div>
        </div>
        <div className="p-5 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-3">
          {skills.map(s => {
            const isUser = s.id.startsWith('user.')
            return (
              <div key={s.id} className={`bg-slate-50/60 border rounded-xl p-4 transition-all ${
                s.runnable ? 'border-slate-200 hover:border-brand-300 hover:bg-white' : 'border-slate-200 opacity-80'
              } ${isUser ? 'border-purple-200 bg-gradient-to-br from-purple-50/40 to-white' : ''}`}>
                <div className="flex items-center justify-between mb-2 gap-2">
                  <div className="flex items-center gap-1.5 min-w-0 flex-1">
                    <span className="text-[10px] text-slate-400 font-mono truncate">{s.id}</span>
                    <span className="text-[10px] text-slate-400">phase={s.phase}</span>
                    {isUser && <span className="text-[10px] bg-purple-100 text-purple-700 px-1.5 rounded">用户</span>}
                  </div>
                  {s.runnable ? (
                    <ToggleSwitch on={s.enabled} loading={busy === s.id} onClick={() => toggle(s)} />
                  ) : (
                    <span className="text-[10px] text-slate-400">声明</span>
                  )}
                </div>
                <div className="font-medium text-sm mb-1 flex items-center gap-1.5">
                  {s.runnable && s.enabled && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />}
                  {s.name}
                </div>
                <div className="text-xs text-slate-600 leading-relaxed mb-2.5">{s.description}</div>
                <div className="flex items-center justify-between">
                  <div className="flex flex-wrap gap-1">
                    <span className="badge badge-rule text-xs">{s.scope}</span>
                    {s.layers.map(l => (<span key={l} className={`layer-tag layer-${l}`}>{l}</span>))}
                  </div>
                  {isUser && (
                    <div className="flex gap-1">
                      <button onClick={() => onEdit(s)} className="text-slate-400 hover:text-brand-500 p-1" title="编辑"><Pencil className="w-3.5 h-3.5" /></button>
                      <button onClick={() => onDelete(s)} className="text-slate-400 hover:text-rose-500 p-1" title="删除"><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
      {editing && <UserSkillEditor form={editing} onCancel={() => setEditing(null)} onSaved={async () => { setEditing(null); await refresh() }} />}
    </div>
  )
}

function ToggleSwitch({ on, loading, onClick }: { on: boolean; loading: boolean; onClick: () => void }) {
  return (
    <div onClick={onClick}
         className={`w-9 h-5 rounded-full relative transition-colors cursor-pointer ${
           loading ? 'bg-slate-300 animate-pulse' : on ? 'bg-brand-500' : 'bg-slate-300'
         }`}>
      <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${on ? 'left-[18px]' : 'left-0.5'}`} />
    </div>
  )
}

function UserSkillEditor({ form, onCancel, onSaved }: {
  form: FormState; onCancel: () => void; onSaved: () => void
}) {
  const [s, setS] = useState(form)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!s.name.trim() || !s.prompt.trim()) {
      alert('名字和 prompt 必填'); return
    }
    setSaving(true)
    try {
      if (s.id) {
        await api.updateUserSkill(s.id, { name: s.name, description: s.description, prompt: s.prompt, phase: s.phase })
      } else {
        await api.createUserSkill({ name: s.name, description: s.description, prompt: s.prompt, phase: s.phase })
      }
      onSaved()
    } catch (e: any) { alert('保存失败:' + e.message) }
    finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-6" onClick={onCancel}>
      <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden shadow-2xl flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-slate-200 bg-gradient-to-r from-purple-50 to-pink-50 flex items-center justify-between flex-shrink-0">
          <h3 className="font-semibold">{s.id ? '✎ 编辑 Skill' : '✨ 新建 Prompt Skill'}</h3>
          <button onClick={onCancel} className="text-slate-400 hover:text-slate-700"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 overflow-y-auto space-y-3">
          <div>
            <label className="text-xs text-slate-600 mb-1 block">名字</label>
            <input value={s.name} onChange={e => setS({...s, name: e.target.value})}
                   placeholder="例:小说人物口吻一致"
                   className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label className="text-xs text-slate-600 mb-1 block">简介(可选)</label>
            <input value={s.description} onChange={e => setS({...s, description: e.target.value})}
                   placeholder="一句话描述"
                   className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:border-brand-500" />
          </div>
          <div>
            <label className="text-xs text-slate-600 mb-1 block">
              Prompt(LLM 看到的指令)— 末尾会自动追加输出格式约定
            </label>
            <textarea value={s.prompt} onChange={e => setS({...s, prompt: e.target.value})}
                      rows={10}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono outline-none focus:border-brand-500 leading-relaxed" />
            <p className="text-[10px] text-slate-400 mt-1">提示:写清"只查 XX"+"绝不报 XX"+"举几个正例反例",效果最好。</p>
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-xs text-slate-600 mb-1 block">Phase(调度顺序,0-100 越小越先)</label>
              <input type="number" value={s.phase} onChange={e => setS({...s, phase: parseInt(e.target.value || '50')})}
                     min={0} max={100}
                     className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:border-brand-500" />
              <p className="text-[10px] text-slate-400 mt-1">建议 40-60(L4=30 之后)</p>
            </div>
          </div>
        </div>
        <div className="px-5 py-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-2 flex-shrink-0">
          <button onClick={onCancel} className="btn btn-secondary">取消</button>
          <button onClick={save} disabled={saving} className="btn btn-primary">
            {saving ? '保存中…' : '✓ 保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

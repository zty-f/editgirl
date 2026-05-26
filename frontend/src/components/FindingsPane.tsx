import { useState } from 'react'
import { Check, X, Pencil, Undo, Sparkles, MessageCircle } from 'lucide-react'
import type { Finding } from '../lib/api'

interface Props {
  findings: Finding[]
  selectedId: string | null
  onSelect: (id: string) => void
  onAccept: (id: string) => void
  onReject: (id: string, reason: string) => void
  onUndo: (id: string) => void
  onEdit: (id: string, final_text: string) => void
}

type Tab = 'pending' | 'accepted' | 'rejected' | 'failed'

export default function FindingsPane({ findings, selectedId, onSelect, onAccept, onReject, onUndo, onEdit }: Props) {
  const [tab, setTab] = useState<Tab>('pending')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const counts = {
    pending: findings.filter(f => f.status === 'pending').length,
    accepted: findings.filter(f => f.status === 'accepted' || f.status === 'edited').length,
    rejected: findings.filter(f => f.status === 'rejected').length,
    failed: findings.filter(f => f.status === 'failed').length,
  }

  const filtered = findings.filter(f => {
    if (tab === 'accepted') return f.status === 'accepted' || f.status === 'edited'
    return f.status === tab
  }).sort((a, b) => {
    // chat / user 类置顶
    if (a.source === 'chat' || a.source === 'user_direct') {
      if (b.source !== 'chat' && b.source !== 'user_direct') return -1
    } else if (b.source === 'chat' || b.source === 'user_direct') return 1
    return a.paragraph_idx - b.paragraph_idx || a.char_start - b.char_start
  })

  const openEdit = (f: Finding) => { setEditingId(f.id); setEditText(f.suggestion) }
  const submitEdit = () => { if (editingId) onEdit(editingId, editText); setEditingId(null) }
  const openReject = (f: Finding) => { setRejectingId(f.id); setRejectReason('') }
  const submitReject = () => { if (rejectingId) onReject(rejectingId, rejectReason); setRejectingId(null) }

  return (
    <>
      <div className="px-4 py-2.5 border-b border-slate-200 bg-slate-50 flex items-center gap-3 flex-shrink-0">
        <div className="text-sm font-semibold">🔍 校对发现</div>
        <div className="ml-auto flex gap-0.5 bg-slate-200/60 p-0.5 rounded-md text-xs">
          {(['pending', 'accepted', 'rejected', 'failed'] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-2 py-1 rounded transition-all ${
                tab === t ? 'bg-white text-slate-900 shadow-sm font-medium' : 'text-slate-600 hover:text-slate-900'
              } ${t === 'failed' && counts.failed === 0 ? 'hidden' : ''}`}>
              {t === 'pending' ? '待处理' : t === 'accepted' ? '已接受' : t === 'rejected' ? '已拒绝' : '⚠失败'}
              <span className="ml-1 text-slate-400">{counts[t]}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {filtered.length === 0 ? (
          <div className="text-center py-16 text-slate-400 text-sm">
            <Sparkles className="w-10 h-10 mx-auto opacity-30 mb-3" />
            <p>{tab === 'pending' ? '点上方「开始校对」' : '暂无'}</p>
          </div>
        ) : filtered.map(f => (
          <FindingCard key={f.id} f={f} selected={f.id === selectedId} onSelect={onSelect}
                       onAccept={onAccept} onReject={openReject} onEdit={openEdit} onUndo={onUndo} />
        ))}
      </div>

      {/* 编辑弹窗 */}
      {editingId && (
        <Modal onClose={() => setEditingId(null)} title="✎ 编辑改法">
          <input value={editText} onChange={e => setEditText(e.target.value)}
                 className="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:border-brand-500 outline-none"
                 onKeyDown={e => e.key === 'Enter' && submitEdit()} autoFocus />
          <div className="flex justify-end gap-2 mt-4">
            <button className="btn btn-secondary" onClick={() => setEditingId(null)}>取消</button>
            <button className="btn btn-primary" onClick={submitEdit}>应用</button>
          </div>
        </Modal>
      )}
      {rejectingId && (
        <Modal onClose={() => setRejectingId(null)} title="✗ 拒绝(填了理由会学规则)">
          <input value={rejectReason} onChange={e => setRejectReason(e.target.value)}
                 placeholder="例:这是方言不要改 / 是引文不能动"
                 className="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:border-brand-500 outline-none"
                 onKeyDown={e => e.key === 'Enter' && submitReject()} autoFocus />
          <div className="flex justify-end gap-2 mt-4">
            <button className="btn btn-secondary" onClick={() => setRejectingId(null)}>取消</button>
            <button className="btn btn-primary" onClick={submitReject}>拒绝</button>
          </div>
        </Modal>
      )}
    </>
  )
}

function FindingCard({ f, selected, onSelect, onAccept, onReject, onEdit, onUndo }: {
  f: Finding; selected: boolean;
  onSelect: (id: string) => void;
  onAccept: (id: string) => void;
  onReject: (f: Finding) => void;
  onEdit: (f: Finding) => void;
  onUndo: (id: string) => void;
}) {
  const isPending = f.status === 'pending'
  const sourceBadge = f.source === 'chat' ? '💬 对话建议'
    : f.source === 'user_direct' ? '✏️ 你的修改' : null
  return (
    <div onClick={() => onSelect(f.id)}
         className={`relative bg-white border rounded-xl p-3 cursor-pointer transition-all hover:shadow-md
                    ${selected ? 'border-brand-500 ring-2 ring-brand-500/20' : 'border-slate-200 hover:border-slate-400'}
                    ${f.status === 'accepted' || f.status === 'edited' ? 'opacity-80' : ''}
                    ${f.status === 'failed' ? 'bg-orange-50 border-orange-200' : ''}`}>
      {sourceBadge && (
        <span className="absolute -top-2 right-3 text-[10px] bg-gradient-to-r from-purple-500 to-pink-500
                         text-white px-2 py-0.5 rounded-full font-medium">
          {sourceBadge}
        </span>
      )}
      <div className="flex flex-wrap gap-1.5 mb-2 text-[10px]">
        <span className="text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">段 {f.paragraph_idx}</span>
        <span className={`layer-tag layer-${f.layer}`}>{f.layer}</span>
        <span className="layer-tag bg-slate-200 text-slate-700">{f.type}</span>
        <span className={`layer-tag conf-${f.confidence}`}>{f.confidence}</span>
      </div>
      <div className="bg-slate-50 -mx-1 px-3 py-2 rounded border-l-2 border-brand-500 mb-2 text-sm font-serif leading-relaxed">
        <span className="text-slate-400 line-through">{f.original}</span>
        <span className="text-slate-400 mx-2">→</span>
        <span className="text-rose-600 font-medium">{f.suggestion || <em className="text-slate-400">(删除)</em>}</span>
      </div>
      {f.explanation && <div className="text-xs text-slate-500 leading-relaxed mb-2">{f.explanation}</div>}
      <div className="flex gap-1.5">
        {isPending ? (
          <>
            <button onClick={e => { e.stopPropagation(); onAccept(f.id) }} className="btn btn-success flex-1 text-xs justify-center"><Check className="w-3.5 h-3.5" />接受</button>
            <button onClick={e => { e.stopPropagation(); onReject(f) }} className="btn btn-danger flex-1 text-xs justify-center"><X className="w-3.5 h-3.5" />拒绝</button>
            <button onClick={e => { e.stopPropagation(); onEdit(f) }} className="btn btn-secondary flex-1 text-xs justify-center"><Pencil className="w-3.5 h-3.5" />编辑</button>
          </>
        ) : f.status === 'failed' ? (
          <>
            <button onClick={e => { e.stopPropagation(); onEdit(f) }} className="btn btn-secondary flex-1 text-xs justify-center"><Pencil className="w-3.5 h-3.5" />手动改</button>
            <button onClick={e => { e.stopPropagation(); onReject(f) }} className="btn btn-danger flex-1 text-xs justify-center"><X className="w-3.5 h-3.5" />放弃</button>
          </>
        ) : (
          <button onClick={e => { e.stopPropagation(); onUndo(f.id) }} className="btn btn-secondary w-full text-xs justify-center"><Undo className="w-3.5 h-3.5" />撤销</button>
        )}
      </div>
    </div>
  )
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-[450px] shadow-2xl" onClick={e => e.stopPropagation()}>
        <h3 className="font-semibold mb-3">{title}</h3>
        {children}
      </div>
    </div>
  )
}

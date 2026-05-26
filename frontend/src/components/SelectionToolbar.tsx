import { useEffect, useState } from 'react'
import { Pencil, Trash2, Lightbulb } from 'lucide-react'
import { api, type Alternative } from '../lib/api'

interface Props {
  docId: string
  onDirectChange: (paragraph_idx: number, selected_text: string, new_text: string, note?: string) => void
}

export default function SelectionToolbar({ docId, onDirectChange }: Props) {
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  const [info, setInfo] = useState<{ paragraph_idx: number; text: string } | null>(null)
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const [showAlts, setShowAlts] = useState(false)
  const [alts, setAlts] = useState<Alternative[]>([])
  const [altsLoading, setAltsLoading] = useState(false)

  useEffect(() => {
    const onMouseUp = () => setTimeout(updateSelection, 10)
    document.addEventListener('mouseup', onMouseUp)
    return () => document.removeEventListener('mouseup', onMouseUp)
  }, [])

  const updateSelection = () => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) { hide(); return }
    const range = sel.getRangeAt(0)
    let node = range.commonAncestorContainer as any
    if (node.nodeType === Node.TEXT_NODE) node = node.parentElement
    let paraEl: any = node
    while (paraEl && !paraEl.dataset?.idx) paraEl = paraEl.parentElement
    if (!paraEl) { hide(); return }
    const text = sel.toString()
    if (!text || text.length > 200) { hide(); return }
    const rect = range.getBoundingClientRect()
    setInfo({ paragraph_idx: parseInt(paraEl.dataset.idx), text })
    setPos({
      left: Math.max(8, Math.min(window.innerWidth - 240, rect.left + rect.width / 2 - 120)),
      top: rect.top - 48,
    })
  }

  const hide = () => { setPos(null); setInfo(null) }

  const onEdit = () => {
    if (!info) return
    setEditValue(info.text); setEditing(true)
  }

  const onDelete = async () => {
    if (!info) return
    if (!confirm(`确定删除"${info.text}"?`)) return
    await onDirectChange(info.paragraph_idx, info.text, '', '用户直接删除')
    hide()
  }

  const onAlts = async () => {
    if (!info) return
    setShowAlts(true); setAltsLoading(true)
    try {
      const data = await api.suggestAlts(docId, {
        paragraph_idx: info.paragraph_idx, selected_text: info.text,
      })
      setAlts(data.alternatives)
    } finally { setAltsLoading(false) }
  }

  const submitEdit = async () => {
    if (!info) return
    await onDirectChange(info.paragraph_idx, info.text, editValue, '用户修改')
    setEditing(false); hide()
  }

  const useAlt = async (alt: Alternative) => {
    if (!info) return
    await onDirectChange(info.paragraph_idx, info.text, alt.text, `AI 候选(${alt.label}):${alt.reason}`)
    setShowAlts(false); hide()
  }

  return (
    <>
      {pos && (
        <div className="fixed z-30 flex bg-white border border-slate-200 rounded-lg shadow-xl p-1"
             style={{ left: pos.left, top: pos.top }}
             onMouseDown={e => e.preventDefault()}>
          <button onClick={onEdit} className="px-2.5 py-1 text-xs hover:bg-slate-100 rounded flex items-center gap-1">
            <Pencil className="w-3 h-3" /> 改
          </button>
          <button onClick={onDelete} className="px-2.5 py-1 text-xs hover:bg-rose-50 hover:text-rose-600 rounded flex items-center gap-1">
            <Trash2 className="w-3 h-3" /> 删
          </button>
          <button onClick={onAlts} className="px-2.5 py-1 text-xs hover:bg-amber-50 hover:text-amber-600 rounded flex items-center gap-1">
            <Lightbulb className="w-3 h-3" /> 求建议
          </button>
        </div>
      )}

      {editing && info && (
        <Modal onClose={() => setEditing(false)} title="改成">
          <div className="text-xs text-slate-500 mb-2">原文:<span className="bg-slate-100 px-1 rounded">{info.text}</span></div>
          <input value={editValue} onChange={e => setEditValue(e.target.value)}
                 className="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:border-brand-500 outline-none"
                 onKeyDown={e => e.key === 'Enter' && submitEdit()} autoFocus />
          <div className="flex justify-end gap-2 mt-4">
            <button className="btn btn-secondary" onClick={() => setEditing(false)}>取消</button>
            <button className="btn btn-primary" onClick={submitEdit}>应用</button>
          </div>
        </Modal>
      )}

      {showAlts && info && (
        <Modal onClose={() => setShowAlts(false)} title="💡 3 个候选改法">
          <div className="text-xs text-slate-500 mb-3">原文:<span className="bg-slate-100 px-1 rounded">{info.text}</span></div>
          {altsLoading ? (
            <div className="text-center py-8 text-slate-400">AI 思考中…</div>
          ) : alts.length === 0 ? (
            <div className="text-center py-8 text-slate-400">没拿到候选。</div>
          ) : (
            <div className="space-y-2">
              {alts.map((a, i) => (
                <div key={i} onClick={() => useAlt(a)}
                     className="border border-slate-200 hover:border-brand-500 hover:bg-brand-50/30 rounded-lg p-3 cursor-pointer transition-all">
                  <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full mb-1.5 inline-block font-medium">
                    {a.label}
                  </span>
                  <div className="font-serif text-sm mb-1">{a.text}</div>
                  <div className="text-xs text-slate-500">💭 {a.reason}</div>
                </div>
              ))}
            </div>
          )}
          <div className="flex justify-end gap-2 mt-4">
            <button className="btn btn-secondary" onClick={() => setShowAlts(false)}>关闭</button>
          </div>
        </Modal>
      )}
    </>
  )
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-[480px] max-h-[80vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
        <h3 className="font-semibold mb-3">{title}</h3>
        {children}
      </div>
    </div>
  )
}

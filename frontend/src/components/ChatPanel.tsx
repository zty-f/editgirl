import { useEffect, useRef, useState } from 'react'
import { MessageCircle, Send, ChevronUp, ChevronDown, Sparkles, GripHorizontal } from 'lucide-react'
import type { ChatMsg } from '../lib/api'

interface Props {
  messages: ChatMsg[]
  onSend: (msg: string) => Promise<void>
}

const STORAGE_KEY = 'editgirl.chat.height'
const DEFAULT_HEIGHT = 260
const MIN_HEIGHT = 120
const MAX_HEIGHT = 600

export default function ChatPanel({ messages, onSend }: Props) {
  const [open, setOpen] = useState(true)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [height, setHeight] = useState<number>(() => {
    const saved = Number(localStorage.getItem(STORAGE_KEY))
    return saved >= MIN_HEIGHT && saved <= MAX_HEIGHT ? saved : DEFAULT_HEIGHT
  })
  const logRef = useRef<HTMLDivElement>(null)
  const draggingRef = useRef(false)

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [messages, open, height])

  // 拖拉调整高度
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return
      const newH = window.innerHeight - e.clientY
      const clamped = Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, newH))
      setHeight(clamped)
    }
    const onUp = () => {
      if (draggingRef.current) {
        draggingRef.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
        localStorage.setItem(STORAGE_KEY, String(height))
      }
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
  }, [height])

  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault()
    draggingRef.current = true
    document.body.style.cursor = 'ns-resize'
    document.body.style.userSelect = 'none'
  }

  const send = async () => {
    const text = input.trim()
    if (!text || sending) return
    setInput(''); setSending(true)
    try { await onSend(text) } finally { setSending(false) }
  }

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault(); send()
    }
  }

  return (
    <div className="border-t border-slate-200 bg-white flex-shrink-0 flex flex-col"
         style={open ? { height } : undefined}>
      {/* 拖拽条 — 只在展开时显示 */}
      {open && (
        <div onMouseDown={startDrag}
             className="group h-1.5 cursor-ns-resize bg-slate-100 hover:bg-brand-300 transition-colors flex items-center justify-center flex-shrink-0">
          <GripHorizontal className="w-4 h-4 text-slate-400 group-hover:text-brand-600 opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      )}
      <button onClick={() => setOpen(!open)}
              className="w-full px-5 py-2 flex items-center gap-2 text-sm text-slate-600 hover:bg-slate-50 transition-colors flex-shrink-0">
        <MessageCircle className="w-4 h-4 text-purple-500" />
        <span className="font-medium">和校对女孩聊</span>
        <span className="text-xs text-slate-400 ml-2">教规则、提改法、问解释</span>
        <div className="ml-auto flex items-center gap-2">
          {messages.length > 0 && (
            <span className="text-xs text-slate-400">{messages.length} 条</span>
          )}
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </div>
      </button>
      {open && (
        <>
          <div ref={logRef} className="flex-1 px-5 py-3 overflow-y-auto bg-gradient-to-b from-slate-50 to-white min-h-0">
            {messages.length === 0 ? (
              <div className="text-center py-8 text-slate-400 text-sm">
                <Sparkles className="w-8 h-8 mx-auto opacity-30 mb-2" />
                还没有对话。试试说"以后引号内方言不要改"或"把第3段X改成Y"
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map(m => <Bubble key={m.id} m={m} />)}
              </div>
            )}
          </div>
          <div className="px-3 py-2 flex gap-2 border-t border-slate-100 bg-white flex-shrink-0">
            <textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKey}
                      placeholder="问问题 / 教规则 / 提改法,Enter 发送 · Shift+Enter 换行"
                      rows={1}
                      className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm
                                  resize-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 outline-none" />
            <button onClick={send} disabled={!input.trim() || sending}
                    className="btn btn-primary"><Send className="w-4 h-4" /></button>
          </div>
        </>
      )}
    </div>
  )
}

function Bubble({ m }: { m: ChatMsg }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] bg-brand-500 text-white px-3.5 py-2 rounded-2xl rounded-tr-sm text-sm whitespace-pre-wrap">
          {m.content}
        </div>
      </div>
    )
  }
  const isRec = m.metadata?.kind === 'recommendation'
  const isSys = m.metadata?.kind === 'system'
  return (
    <div className="flex gap-2">
      <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs
                       ${isRec ? 'bg-gradient-to-br from-amber-400 to-orange-500 text-white'
                              : isSys ? 'bg-gradient-to-br from-emerald-400 to-teal-500 text-white'
                              : 'bg-gradient-to-br from-purple-500 to-blue-500 text-white'}`}>
        {isRec ? '💡' : isSys ? '⚙' : '📝'}
      </div>
      <div className={`max-w-[80%] px-3.5 py-2 rounded-2xl rounded-tl-sm text-sm whitespace-pre-wrap border
                       ${isRec ? 'bg-amber-50 border-amber-200 text-slate-800'
                              : isSys ? 'bg-emerald-50 border-emerald-200 text-slate-800'
                              : 'bg-slate-100 border-slate-200 text-slate-800'}`}>
        {m.content}
      </div>
    </div>
  )
}

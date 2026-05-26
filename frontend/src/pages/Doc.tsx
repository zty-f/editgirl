import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Play, Download, RefreshCw, Sparkles, Settings } from 'lucide-react'
import { api, type DocumentItem, type Finding, type Preview, type State, type ChatMsg } from '../lib/api'
import FindingsPane from '../components/FindingsPane'
import DocxPreview from '../components/DocxPreview'
import ChatPanel from '../components/ChatPanel'
import SelectionToolbar from '../components/SelectionToolbar'
import SkillsModal from '../components/SkillsModal'
import SettingsModal from '../components/SettingsModal'

export default function DocPage() {
  const { docId } = useParams<{ docId: string }>()
  const [doc, setDoc] = useState<DocumentItem | null>(null)
  const [findings, setFindings] = useState<Finding[]>([])
  const [preview, setPreview] = useState<Preview | null>(null)
  const [state, setState] = useState<State>({ pending: 0, accepted: 0, rejected: 0, failed: 0, total: 0 })
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [proofreading, setProofreading] = useState(false)
  const [progress, setProgress] = useState<{ stage: string; pct: number } | null>(null)
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null)
  const [showSkills, setShowSkills] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  // 加载文档
  useEffect(() => {
    if (!docId) return
    api.getDoc(docId).then(d => {
      setDoc(d)
      // push 一条系统消息,告知用户文档已加载
      const sysMsg: ChatMsg = {
        id: 'sys-load-' + Date.now(), doc_id: docId, role: 'assistant',
        content: `📂 已加载 ${d.filename} · ${d.paragraph_count} 段 · ${d.word_count} 字\n点上方「▶ 开始校对」开始,或在下面直接和我说话。`,
        metadata: { kind: 'system' },
        created_at: new Date().toISOString(),
      }
      setMessages(prev => prev.length === 0 ? [sysMsg] : prev)
    }).catch(e => console.error(e))
    refreshAll()
    api.getMessages(docId).then(prev => setMessages(p => prev.length > 0 ? prev : p))
    openWS()
    return () => { wsRef.current?.close() }
  }, [docId])

  const refreshAll = async () => {
    if (!docId) return
    const [fs, pv] = await Promise.all([api.listErrors(docId), api.preview(docId)])
    setFindings(fs)
    setPreview(pv)
    // state 来自 last action 的返回,但也可以从 findings 算
    setState({
      pending: fs.filter(f => f.status === 'pending').length,
      accepted: fs.filter(f => f.status === 'accepted' || f.status === 'edited').length,
      rejected: fs.filter(f => f.status === 'rejected').length,
      failed: fs.filter(f => f.status === 'failed').length,
      total: fs.length,
    })
  }

  const openWS = () => {
    if (!docId) return
    if (wsRef.current) wsRef.current.close()
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/api/ws/${docId}`)
    ws.onopen = () => console.log('[WS] connected')
    ws.onerror = (e) => console.error('[WS] error', e)
    ws.onclose = () => console.log('[WS] closed')
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'proofread_progress') {
          const pct = msg.total ? Math.min(95, Math.round(msg.done / msg.total * 95)) : 30
          setProgress({ stage: msg.stage, pct })
        } else if (msg.type === 'proofread_done') {
          setProgress({ stage: '完成', pct: 100 })
          setTimeout(() => setProgress(null), 2000)
        } else if (msg.type === 'assistant_message') {
          // 推送的智能推荐
          setMessages(prev => [...prev, {
            id: 'rec-' + Date.now(), doc_id: docId, role: 'assistant',
            content: msg.text, metadata: { kind: 'recommendation' },
            created_at: new Date().toISOString(),
          }])
        } else if (msg.type === 'l5_warning') {
          // 后台 L5 报告
          refreshAll()
        }
      } catch {}
    }
    wsRef.current = ws
  }

  const runProofread = async () => {
    if (!docId || !doc) return
    setProofreading(true)
    // 估算时间(每 10 段一批,每批 LLM ~30s,6 并发)
    const batches = Math.ceil(doc.paragraph_count / 10)
    const estSec = Math.ceil(batches / 6 * 30)
    setProgress({
      stage: `准备中… (${doc.paragraph_count} 段 / ${batches} 批 / 估算 ${estSec > 60 ? Math.ceil(estSec/60) + '分钟' : estSec + '秒'})`,
      pct: 2,
    })
    // 系统消息提醒
    setMessages(prev => [...prev, {
      id: 'sys-' + Date.now(), doc_id: docId, role: 'assistant',
      content: `🚀 开始校对(共 ${doc.paragraph_count} 段,预计 ${estSec > 60 ? Math.ceil(estSec/60) + ' 分钟' : estSec + ' 秒'})\n   进度会在顶部条实时显示,完成后自动加载结果。`,
      metadata: { kind: 'system' },
      created_at: new Date().toISOString(),
    }])
    try {
      const data = await api.proofread(docId)
      setState(data.state)
      await refreshAll()
      setMessages(prev => [...prev, {
        id: 'sys-' + Date.now(), doc_id: docId, role: 'assistant',
        content: `✅ 校对完成,新发现 ${data.new} 处:` +
          Object.entries(data.by_layer).map(([l,n])=>`${l} ${n}`).join(', '),
        metadata: { kind: 'system' },
        created_at: new Date().toISOString(),
      }])
      setProgress({ stage: `✅ 完成,共 ${data.new} 处`, pct: 100 })
    } catch (e: any) {
      alert('校对失败:' + e.message)
      setProgress(null)
    } finally {
      setProofreading(false)
      // 不管 WS 有没有 push proofread_done,自己保证 2s 后清进度条
      setTimeout(() => setProgress(null), 2000)
    }
  }

  const onExport = async () => {
    if (!docId) return
    try {
      await api.export(docId)
      window.location.href = api.downloadUrl(docId)
    } catch (e: any) {
      alert(e.message)
    }
  }

  const onAccept = async (fid: string) => {
    const data = await api.acceptError(fid)
    setState(data.state)
    setSelectedFindingId(fid)
    await refreshAll()
    if (data.l5_warnings > 0) {
      // L5 已经入 errors,refresh 后会显示
    }
  }

  const onReject = async (fid: string, reason: string) => {
    const data = await api.rejectError(fid, reason)
    setState(data.state)
    await refreshAll()
  }

  const onUndo = async (fid: string) => {
    const data = await api.undoError(fid)
    setState(data.state)
    await refreshAll()
  }

  const onEdit = async (fid: string, final_text: string) => {
    const data = await api.acceptError(fid, { final_text })
    setState(data.state)
    setSelectedFindingId(fid)
    await refreshAll()
  }

  const onBatchAccept = async (filter: any) => {
    if (!docId) return
    await api.batchAccept(docId, filter)
    await refreshAll()
  }

  const onBatchReject = async () => {
    if (!docId) return
    if (!confirm('确定拒绝全部待处理?')) return
    await api.batchReject(docId, {})
    await refreshAll()
  }

  const onChat = async (msg: string) => {
    if (!docId) return
    // 先 push 用户消息
    setMessages(prev => [...prev, {
      id: 'u-' + Date.now(), doc_id: docId, role: 'user',
      content: msg, metadata: {}, created_at: new Date().toISOString(),
    }])
    const data = await api.sendChat(docId, msg)
    setMessages(prev => [...prev, {
      id: 'a-' + Date.now(), doc_id: docId, role: 'assistant',
      content: data.reply, metadata: {}, created_at: new Date().toISOString(),
    }])
    setState(data.state)
    if (data.new_edits > 0) await refreshAll()
  }

  const onDirectChange = async (paragraph_idx: number, selected_text: string,
                                  new_text: string, note: string = '') => {
    if (!docId) return
    const data = await api.directChange(docId, { paragraph_idx, selected_text, new_text, note })
    setState(data.state)
    setSelectedFindingId(data.finding_id)
    await refreshAll()
  }

  return (
    <div className="h-screen flex flex-col">
      {/* 顶栏 */}
      <header className="px-5 py-3 flex items-center gap-3 border-b border-slate-200 bg-white/95 backdrop-blur flex-shrink-0">
        <Link to="/" className="text-slate-500 hover:text-slate-900"><ArrowLeft className="w-5 h-5" /></Link>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold truncate">{doc?.filename || '加载中...'}</div>
          <div className="text-xs text-slate-500">
            {doc?.paragraph_count} 段 · {doc?.word_count} 字
          </div>
        </div>
        <button className="btn btn-primary" onClick={runProofread} disabled={proofreading}>
          {proofreading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {proofreading ? '校对中…' : '开始校对'}
        </button>
        <button className="btn btn-secondary" onClick={onExport}>
          <Download className="w-4 h-4" /> 导出
        </button>
        <button className="btn btn-ghost" onClick={() => setShowSkills(true)} title="开关 skill,实时生效">
          <Sparkles className="w-4 h-4" /> Skills
        </button>
        <button className="btn btn-ghost" onClick={() => setShowSettings(true)} title="切换 LLM 模型">
          <Settings className="w-4 h-4" />
        </button>
      </header>

      {/* 进度条 */}
      {progress && (
        <div className="h-7 relative overflow-hidden bg-brand-50 border-b border-brand-100 flex-shrink-0">
          <div
            className="absolute inset-y-0 left-0 bg-gradient-to-r from-brand-500 to-purple-500 opacity-80 transition-all duration-300"
            style={{ width: `${progress.pct}%` }}
          />
          <div className="absolute inset-0 flex items-center justify-center text-xs font-medium text-slate-800">
            {progress.stage}
          </div>
        </div>
      )}

      {/* 状态条 */}
      <div className="px-5 py-2 flex items-center gap-2 bg-white border-b border-slate-200 flex-shrink-0">
        <span className="badge badge-pending">⏳ 待处理 {state.pending}</span>
        <span className="badge badge-accept">✓ 已接受 {state.accepted}</span>
        <span className="badge badge-reject">✗ 已拒绝 {state.rejected}</span>
        {state.failed > 0 && <span className="badge badge-failed">⚠ 失败 {state.failed}</span>}
        <div className="flex-1" />
        <div className="flex gap-2">
          <button className="btn btn-secondary text-xs" onClick={() => onBatchAccept({ confidence: 'high' })}
                  disabled={state.pending === 0}>
            ✓ 接受全部高置信
          </button>
          <button className="btn btn-secondary text-xs" onClick={() => onBatchAccept({})}
                  disabled={state.pending === 0}>
            ✓ 全部接受
          </button>
          <button className="btn btn-danger text-xs" onClick={onBatchReject}
                  disabled={state.pending === 0}>
            ✗ 全部拒绝
          </button>
        </div>
      </div>

      {/* 主体:左 docx,右 findings */}
      <main className="flex-1 grid grid-cols-[1.5fr_1fr] gap-3 p-3 min-h-0">
        <section className="bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col overflow-hidden">
          <div className="px-4 py-2.5 border-b border-slate-200 bg-slate-50 flex items-center justify-between flex-shrink-0">
            <div className="text-sm font-semibold">📄 文档预览</div>
            <div className="text-xs text-slate-500">
              <span className="text-rose-700 underline">红下划线</span>=新增
              <span className="text-slate-400 line-through ml-2">灰删除线</span>=删除
            </div>
          </div>
          <DocxPreview
            preview={preview}
            highlightParagraph={findings.find(f => f.id === selectedFindingId)?.paragraph_idx}
            onDirectChange={onDirectChange}
            docId={docId!}
          />
        </section>
        <section className="bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col overflow-hidden">
          <FindingsPane
            findings={findings}
            selectedId={selectedFindingId}
            onSelect={setSelectedFindingId}
            onAccept={onAccept}
            onReject={onReject}
            onUndo={onUndo}
            onEdit={onEdit}
          />
        </section>
      </main>

      {/* 底部聊天 */}
      <ChatPanel messages={messages} onSend={onChat} />

      <SelectionToolbar docId={docId!} onDirectChange={onDirectChange} />
      <SkillsModal open={showSkills} onClose={() => setShowSkills(false)} />
      <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
    </div>
  )
}

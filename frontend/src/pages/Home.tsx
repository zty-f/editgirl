import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Upload, FileText, Trash2, Cog, Sparkles } from 'lucide-react'
import { api, type DocumentItem } from '../lib/api'

export default function Home() {
  const [docs, setDocs] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const nav = useNavigate()

  const refresh = async () => {
    try { setDocs(await api.listDocs()) } catch (e: any) { setError(e.message) }
  }
  useEffect(() => { refresh() }, [])

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setLoading(true); setError('')
    try {
      const doc = await api.upload(f)
      nav(`/doc/${doc.id}`)
    } catch (e: any) {
      setError(e.message)
    } finally { setLoading(false) }
  }

  const onDelete = async (id: string) => {
    if (!confirm('确定删除这份文档及其所有 finding/聊天?')) return
    await api.deleteDoc(id)
    refresh()
  }

  return (
    <div className="min-h-screen">
      <header className="px-8 py-5 flex items-center gap-4 border-b border-slate-200 bg-white/80 backdrop-blur">
        <Sparkles className="w-6 h-6 text-brand-500" />
        <h1 className="text-xl font-semibold bg-gradient-to-r from-brand-600 to-purple-600 bg-clip-text text-transparent">
          校对女孩
        </h1>
        <span className="text-sm text-slate-500">智能体校对助手 · v0.1</span>
        <div className="ml-auto flex gap-2">
          <Link to="/skills" className="btn btn-ghost"><Cog className="w-4 h-4" /> 能力中心</Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-8 py-10">
        <div className="mb-8">
          <h2 className="text-2xl font-bold mb-1">我的文档</h2>
          <p className="text-slate-500 text-sm">所有上传过的稿件、校对状态和对话历史都在这里。</p>
        </div>

        <label className="block mb-6">
          <input type="file" accept=".docx" hidden onChange={onUpload} disabled={loading} />
          <div className={`relative group rounded-xl border-2 border-dashed border-slate-300 hover:border-brand-500
                          bg-white p-10 text-center cursor-pointer transition-all
                          ${loading ? 'opacity-50' : ''}`}>
            <Upload className="w-10 h-10 mx-auto text-slate-400 group-hover:text-brand-500 mb-3" />
            <div className="text-base font-medium text-slate-700">
              {loading ? '上传中...' : '点击或拖入 docx 文件'}
            </div>
            <div className="text-xs text-slate-500 mt-1">只支持 Word .docx 格式</div>
          </div>
        </label>

        {error && <div className="text-rose-600 text-sm mb-4">{error}</div>}

        {docs.length === 0 ? (
          <div className="text-center py-16 text-slate-400">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>还没有文档,上传一份开始</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {docs.map(d => (
              <div key={d.id} className="group bg-white border border-slate-200 hover:border-brand-500
                                          hover:shadow-md transition-all rounded-xl p-4 flex items-center gap-3">
                <Link to={`/doc/${d.id}`} className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <FileText className="w-4 h-4 text-brand-500" />
                    <div className="font-medium truncate">{d.filename}</div>
                  </div>
                  <div className="text-xs text-slate-500">
                    {d.paragraph_count} 段 · {d.word_count} 字
                    <span className="ml-2">· {d.created_at.split('T')[0]}</span>
                  </div>
                </Link>
                <button onClick={() => onDelete(d.id)}
                        className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-500 p-1.5 transition-opacity">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

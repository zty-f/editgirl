import { useEffect, useState } from 'react'
import { X, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { api, type LLMSettings } from '../lib/api'

interface Props { open: boolean; onClose: () => void }

const PRESETS = [
  // OpenAI 兼容
  { provider: 'openai', name: 'OpenAI gpt-4o', base: 'https://api.openai.com/v1', model: 'gpt-4o' },
  { provider: 'openai', name: 'OpenAI gpt-4o-mini', base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { provider: 'openai', name: 'DeepSeek V3', base: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { provider: 'openai', name: 'DeepSeek Reasoner', base: 'https://api.deepseek.com/v1', model: 'deepseek-reasoner' },
  { provider: 'openai', name: '通义千问 Plus', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  { provider: 'openai', name: '通义千问 Turbo', base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-turbo' },
  { provider: 'openai', name: '智谱 GLM-4', base: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-plus' },
  { provider: 'openai', name: 'Moonshot Kimi', base: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-32k' },
  { provider: 'openai', name: 'Ollama 本地', base: 'http://localhost:11434/v1', model: 'qwen2.5:7b' },
  { provider: 'openai', name: '内网 gpt-5.5(当前)', base: 'http://10.118.65.121:8080/v1', model: 'gpt-5.5' },
  // Anthropic
  { provider: 'anthropic', name: 'Claude Opus 4.7', base: 'https://api.anthropic.com', model: 'claude-opus-4-7' },
  { provider: 'anthropic', name: 'Claude Sonnet 4.6', base: 'https://api.anthropic.com', model: 'claude-sonnet-4-6' },
  { provider: 'anthropic', name: 'Claude Haiku 4.5', base: 'https://api.anthropic.com', model: 'claude-haiku-4-5-20251001' },
] as const

export default function SettingsModal({ open, onClose }: Props) {
  const [current, setCurrent] = useState<LLMSettings | null>(null)
  const [provider, setProvider] = useState<'openai' | 'anthropic'>('openai')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) api.getSettings().then(s => {
      setCurrent(s)
      setProvider(s.LLM_PROVIDER || 'openai')
      setBaseUrl(s.OPENAI_BASE_URL)
      setModel(s.LLM_MODEL)
      setApiKey('')
      setTestResult(null)
    })
  }, [open])

  const usePreset = (p: typeof PRESETS[0]) => {
    setProvider(p.provider as 'openai' | 'anthropic')
    setBaseUrl(p.base); setModel(p.model); setTestResult(null)
  }

  const buildBody = (): any => {
    const body: any = { LLM_PROVIDER: provider, OPENAI_BASE_URL: baseUrl, LLM_MODEL: model }
    if (apiKey) body.OPENAI_API_KEY = apiKey
    return body
  }

  const onTest = async () => {
    setTesting(true); setTestResult(null)
    try {
      const res = await api.testSettings(buildBody())
      setTestResult({ ok: res.ok, msg: res.ok ? `✓ 连接成功:${res.model} 回复 "${res.reply}"` : `✗ ${res.error}` })
    } catch (e: any) {
      setTestResult({ ok: false, msg: '请求失败:' + e.message })
    } finally { setTesting(false) }
  }

  const onSave = async () => {
    setSaving(true)
    try {
      await api.updateSettings(buildBody())
      onClose()
    } catch (e: any) {
      alert('保存失败:' + e.message)
    } finally { setSaving(false) }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-6" onClick={onClose}>
      <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[85vh] overflow-hidden shadow-2xl flex flex-col"
           onClick={e => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-gradient-to-r from-slate-50 to-blue-50 flex-shrink-0">
          <div>
            <h3 className="text-lg font-semibold">⚙️ LLM 模型配置</h3>
            <p className="text-xs text-slate-500 mt-0.5">支持任何 OpenAI 兼容端点。改完保存,下一次校对/对话立即用新模型。</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4">
          {/* 当前 */}
          {current && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-xs">
              <div className="font-medium text-emerald-800 mb-1">当前生效</div>
              <div className="text-emerald-700">Provider: {current.LLM_PROVIDER}</div>
              <div className="text-emerald-700">Base: {current.OPENAI_BASE_URL}</div>
              <div className="text-emerald-700">Key:  {current.OPENAI_API_KEY_masked}</div>
              <div className="text-emerald-700">Model: {current.LLM_MODEL}</div>
            </div>
          )}

          {/* Provider 切换 */}
          <div>
            <label className="text-sm font-medium text-slate-700 mb-2 block">Provider</label>
            <div className="flex gap-2">
              <button onClick={() => setProvider('openai')}
                      className={`flex-1 px-3 py-2 border rounded-lg text-sm transition-all ${
                        provider === 'openai' ? 'border-brand-500 bg-brand-50 text-brand-700 font-medium' : 'border-slate-300 hover:border-slate-400'
                      }`}>
                🟢 OpenAI 兼容
                <div className="text-[10px] text-slate-500 mt-0.5">GPT/DeepSeek/通义/GLM/Ollama 等</div>
              </button>
              <button onClick={() => setProvider('anthropic')}
                      className={`flex-1 px-3 py-2 border rounded-lg text-sm transition-all ${
                        provider === 'anthropic' ? 'border-brand-500 bg-brand-50 text-brand-700 font-medium' : 'border-slate-300 hover:border-slate-400'
                      }`}>
                🤖 Anthropic
                <div className="text-[10px] text-slate-500 mt-0.5">Claude Opus/Sonnet/Haiku</div>
              </button>
            </div>
          </div>

          {/* 预设 */}
          <div>
            <label className="text-sm font-medium text-slate-700 mb-2 block">🚀 一键模板(挑一个再填 API Key)</label>
            <div className="grid grid-cols-2 gap-2">
              {PRESETS.filter(p => p.provider === provider).map(p => (
                <button key={p.name} onClick={() => usePreset(p)}
                        className="text-left text-xs px-3 py-2 bg-slate-50 hover:bg-brand-50 hover:border-brand-300
                                   border border-slate-200 rounded-lg transition-all">
                  <div className="font-medium text-slate-800">{p.name}</div>
                  <div className="text-[10px] text-slate-500 truncate font-mono">{p.model}</div>
                </button>
              ))}
            </div>
          </div>

          {/* 手填 */}
          <div>
            <label className="text-sm font-medium text-slate-700 mb-1 block">Base URL</label>
            <input value={baseUrl} onChange={e => setBaseUrl(e.target.value)}
                   placeholder="https://api.openai.com/v1"
                   className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono outline-none focus:border-brand-500" />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700 mb-1 block">
              API Key <span className="text-xs text-slate-500 font-normal">(留空 = 不修改现有 key)</span>
            </label>
            <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                   placeholder="sk-... 或 留空保留原值"
                   className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono outline-none focus:border-brand-500" />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700 mb-1 block">Model 名</label>
            <input value={model} onChange={e => setModel(e.target.value)}
                   placeholder="gpt-4o / deepseek-chat / qwen-plus / ..."
                   className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono outline-none focus:border-brand-500" />
          </div>

          {testResult && (
            <div className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
              testResult.ok ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'
            }`}>
              {testResult.ok ? <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />}
              <div>{testResult.msg}</div>
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-slate-200 flex justify-between gap-2 bg-slate-50 flex-shrink-0">
          <button onClick={onTest} disabled={testing || !baseUrl || !model}
                  className="btn btn-secondary">
            {testing ? <><Loader2 className="w-4 h-4 animate-spin" /> 测试中...</> : <>🧪 测试连接</>}
          </button>
          <div className="flex gap-2">
            <button onClick={onClose} className="btn btn-secondary">取消</button>
            <button onClick={onSave} disabled={saving || !baseUrl || !model} className="btn btn-primary">
              {saving ? '保存中...' : '✓ 保存并应用'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

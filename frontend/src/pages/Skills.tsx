import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, CheckCircle2 } from 'lucide-react'
import { api, type Skill } from '../lib/api'

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([])
  useEffect(() => { api.listSkills().then(setSkills) }, [])

  return (
    <div className="min-h-screen">
      <header className="px-8 py-5 flex items-center gap-3 border-b border-slate-200 bg-white/80 backdrop-blur">
        <Link to="/" className="text-slate-600 hover:text-slate-900"><ArrowLeft className="w-5 h-5" /></Link>
        <h1 className="text-xl font-semibold">🧩 能力中心(Skills)</h1>
      </header>
      <main className="max-w-4xl mx-auto px-8 py-10">
        <p className="text-slate-500 text-sm mb-6">
          每个 Skill 是一个独立能力单元,可扩展。后续可加用户自定义 / 项目级 Skill。
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {skills.map(s => (
            <div key={s.id} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-slate-400">{s.id}</span>
                {s.enabled && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
              </div>
              <div className="font-medium mb-1">{s.name}</div>
              <div className="text-sm text-slate-600 mb-2">{s.description}</div>
              <div className="flex gap-1">
                <span className="badge badge-rule text-xs">{s.scope}</span>
                {s.layers.map(l => (
                  <span key={l} className={`layer-tag layer-${l}`}>{l}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}

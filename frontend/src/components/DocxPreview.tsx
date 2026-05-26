import { useEffect, useRef } from 'react'
import type { Preview } from '../lib/api'

interface Props {
  preview: Preview | null
  highlightParagraph?: number
  onDirectChange: (paragraph_idx: number, selected_text: string, new_text: string, note?: string) => void
  docId: string
}

export default function DocxPreview({ preview, highlightParagraph }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (highlightParagraph === undefined || !containerRef.current) return
    const target = containerRef.current.querySelector(`[data-idx="${highlightParagraph}"]`)
    if (target) {
      target.classList.add('hl')
      target.scrollIntoView({ block: 'center', behavior: 'smooth' })
      setTimeout(() => target.classList.remove('hl'), 1500)
    }
  }, [highlightParagraph, preview])

  if (!preview) return (
    <div className="flex-1 flex items-center justify-center text-slate-400">加载中…</div>
  )

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto bg-slate-100 p-6">
      <div className="doc-preview">
        {preview.paragraphs.map(p => {
          const Tag = p.style.toLowerCase().startsWith('heading') ? 'h2' : 'p'
          return (
            <Tag key={p.idx} data-idx={p.idx}>
              {p.runs.length === 0 ? ' ' : p.runs.map((r, i) => (
                <span key={i} className={r.type === 'ins' ? 'ins' : r.type === 'del' ? 'del' : ''}>
                  {r.text}
                </span>
              ))}
            </Tag>
          )
        })}
      </div>
    </div>
  )
}

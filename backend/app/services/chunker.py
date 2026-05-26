"""段落分块器(zcheck 风格):按字符上限批量并保留前后上下文。"""
from __future__ import annotations
from dataclasses import dataclass, field
from ..schemas import Paragraph


@dataclass
class Chunk:
    paragraph_start: int
    paragraph_end: int
    paragraphs: list[Paragraph] = field(default_factory=list)
    context_before: str = ""
    context_after: str = ""

    @property
    def total_chars(self) -> int:
        return sum(len(p.text) for p in self.paragraphs)


class Chunker:
    def __init__(self, target_chars: int = 1200, context_chars: int = 200):
        self.target = target_chars
        self.context = context_chars

    def split(self, paragraphs: list[Paragraph]) -> list[Chunk]:
        chunks: list[Chunk] = []
        cur: list[Paragraph] = []
        cur_chars = 0
        for p in paragraphs:
            if cur and cur_chars + len(p.text) > self.target:
                chunks.append(self._make_chunk(cur))
                cur = []
                cur_chars = 0
            cur.append(p)
            cur_chars += len(p.text)
        if cur:
            chunks.append(self._make_chunk(cur))

        # 加上下文
        all_text_by_idx = {p.paragraph_idx: p.text for p in paragraphs}
        sorted_idxs = sorted(all_text_by_idx)
        for c in chunks:
            before_idxs = [i for i in sorted_idxs if i < c.paragraph_start]
            after_idxs = [i for i in sorted_idxs if i > c.paragraph_end]
            before_text = "".join(all_text_by_idx[i] for i in before_idxs[-3:])
            after_text = "".join(all_text_by_idx[i] for i in after_idxs[:3])
            c.context_before = before_text[-self.context:] if before_text else ""
            c.context_after = after_text[:self.context] if after_text else ""
        return chunks

    def _make_chunk(self, ps: list[Paragraph]) -> Chunk:
        return Chunk(
            paragraph_start=ps[0].paragraph_idx,
            paragraph_end=ps[-1].paragraph_idx,
            paragraphs=ps,
        )

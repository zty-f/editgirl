"""Spike: 验证 docx-revisions 能插入 track changes 并被 Word 识别。

验收标准(参考 PRD §5.5):
1. 输入测试 docx,插入多处修订
2. 保存后能在 macOS Word/Pages 打开
3. 修订侧边栏显示作者="校对女孩"
4. 接受所有修订后,文档变成预期文本
5. 拒绝所有修订后,文档恢复原文
6. 中文不乱码
"""
from pathlib import Path
from docx_revisions import RevisionDocument, RevisionParagraph


def spike(in_path: Path, out_path: Path):
    rdoc = RevisionDocument(str(in_path))
    print(f"加载文档:{in_path}")
    print(f"段落数:{len(rdoc.paragraphs)}")

    revisions = [
        (1, "心惊胆颤", "心惊胆战"),
        (2, "山青水秀", "山清水秀"),
        (3, "其", ""),
        (4, "既使", "即使"),
        (6, "大约", ""),
    ]

    applied = 0
    for idx, search, replace in revisions:
        para = rdoc.paragraphs[idx]
        count = para.replace_tracked(search, replace, author="校对女孩")
        if count > 0:
            applied += count
            print(f"  段 {idx}: '{search}' → '{replace}' (作者: 校对女孩)")
        else:
            print(f"  段 {idx}: '{search}' 未找到 ❌")

    rdoc.save(str(out_path))
    print(f"\n应用 {applied} 处修订,已保存到:{out_path}")

    # 二次加载校验修订都在
    rdoc2 = RevisionDocument(str(out_path))
    total_revs = sum(len(p.track_changes) for p in rdoc2.paragraphs)
    print(f"重新加载后修订数:{total_revs}")
    assert total_revs == applied * 2, f"修订应为 {applied*2}(每处 ins+del),实际 {total_revs}"
    print("✅ Spike 通过:修订写入并可读回")


if __name__ == "__main__":
    base = Path(__file__).parent / "fixtures"
    spike(base / "测试文档.docx", base / "测试文档_已修订.docx")

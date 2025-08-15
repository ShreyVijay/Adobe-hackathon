import fitz  # PyMuPDF
import json
import re
from pathlib import Path
from collections import Counter
from difflib import SequenceMatcher


def extract_blocks(doc, y_tol=2.0, x_tol=2.0):
    spans = []
    for page_num, page in enumerate(doc, start=1):
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                current = []
                for span in line["spans"]:
                    txt = span["text"].strip()
                    if not txt:
                        continue
                    x0, y0, x1, y1 = span["bbox"]
                    current.append((x0, y0, x1, y1, txt, span.get("size", 0), span.get("flags", 0)))
                if not current:
                    continue
                current.sort(key=lambda t: t[0])
                merged = []
                last_x1 = None
                for x0, y0, x1, y1, txt, size, flags in current:
                    if last_x1 is not None and x0 - last_x1 > size * 0.3:
                        merged.append(' ')
                    merged.append(txt)
                    last_x1 = x1
                text_line = ''.join(merged)
                spans.append({
                    "text": text_line,
                    "font_size": size,
                    "bold": bool(flags & 2),
                    "page": page_num,
                    "x0": current[0][0],
                    "y0": current[0][1]
                })
    return spans


def deduplicate(text):
    if not text:
        return ""
    chars = list(text)
    result = []
    prev_c = ''
    for c in chars:
        if c != prev_c or not c.isalnum():
            result.append(c)
        prev_c = c
    return ''.join(result)


def detect_title(blocks):
    candidates = [b for b in blocks if b['page'] == 1 and len(b['text'].split()) >= 3]
    if not candidates:
        return ""
    candidates.sort(key=lambda b: (-b['font_size'], -b['y0'], b['x0']))
    for cand in candidates:
        cleaned = deduplicate(cand['text'])
        if len(cleaned.split()) >= 3:
            return cleaned
    return deduplicate(candidates[0]['text'])


def is_similar(a, b, threshold=0.85):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def cluster_font_sizes(blocks):
    freq = Counter(round(b['font_size']) for b in blocks)
    body = freq.most_common(1)[0][0]
    heads = sorted([s for s in freq if s > body], reverse=True)[:4]
    return heads, body


def classify_headings(blocks, title=""):
    heads, body = cluster_font_sizes(blocks)
    items = []
    for b in blocks:
        s = round(b['font_size'])
        t = b['text']
        if not t or is_similar(t, title):
            continue
        if sum(c.isalpha() for c in t) / max(len(t), 1) < 0.4:
            continue
        is_numbered = re.match(r'^(\d+\.\d*|[IVXLCDM]+\.|[A-Z]\.)\s+', t)
        if s in heads:
            lvl = 'H' + str(heads.index(s) + 1)
            if lvl == 'H1' and is_numbered:
                lvl = 'H2'
        elif s > body and b['bold'] and abs(b['x0'] - 150) < 50:
            lvl = 'H3'
        else:
            continue
        fixed_text = deduplicate(t)
        if len(fixed_text.strip()) > 2:
            items.append((b['page'], -b['y0'], b['x0'], {"level": lvl, 'text': fixed_text, 'page': b['page']}))
    items.sort(key=lambda x: (x[0], x[1], x[2]))
    return [i[3] for i in items]


def extract_outline(path):
    doc = fitz.open(path)
    blocks = extract_blocks(doc)
    title = detect_title(blocks)
    outline = classify_headings(blocks, title)
    return {'title': title, 'outline': outline}


def main(inp, outp):
    inp, outp = Path(inp), Path(outp)
    outp.mkdir(exist_ok=True)
    for pdf in inp.glob('*.pdf'):
        print(f"Processing {pdf.name}...")
        res = extract_outline(pdf)
        with open(outp / f'{pdf.stem}.json', 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"  → Completed {pdf.name}\n")
    print("✅ All files processed.")


if __name__ == '__main__':
    import sys
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "/app/input"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "/app/output"
    if len(sys.argv) != 3:
        print('Usage: process_pdfs.py <input_dir> <output_dir>')
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

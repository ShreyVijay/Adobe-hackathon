import fitz  # PyMuPDF
import json
import re
from pathlib import Path
from collections import Counter


def extract_characters(doc, threshold_factor=0.15):
    chars = []
    for page_num, page in enumerate(doc, start=1):
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = span["bbox"]
                    font_size = span.get("size", 0)
                    bold = bool(span.get("flags", 0) & 2)

                    span_width = x1 - x0
                    span_height = y1 - y0
                    char_count = len(text)
                    if char_count == 0 or span_width <= 0:
                        continue

                    base_width = span_width / char_count
                    x_pad = base_width * threshold_factor
                    y_pad = span_height * threshold_factor

                    for i, c in enumerate(text):
                        cx0 = x0 + i * base_width - x_pad
                        cx1 = x0 + (i + 1) * base_width + x_pad
                        cy0 = y0 - y_pad
                        cy1 = y1 + y_pad

                        char_box = {
                            "char": c,
                            "font_size": font_size,
                            "bold": bold,
                            "page": page_num,
                            "x0": round(cx0, 2),
                            "x1": round(cx1, 2),
                            "y0": round(cy0, 2),
                            "y1": round(cy1, 2),
                        }
                        chars.append(char_box)
    return chars


def deduplicate_chars(chars):
    result = []
    seen = set()
    for c in chars:
        width = c['x1'] - c['x0']
        height = c['y1'] - c['y0']
        pad_x = width * 0.3
        pad_y = height * 0.3

        key = (
            c['char'],
            c['bold'],
            round(c['x0'] - pad_x, 1),
            round(c['y0'] - pad_y, 1),
            c['page']
        )
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result


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


def detect_title_and_filter_blocks(blocks, debug_dir=None):
    if not blocks:
        return "", []

    max_font = max(b['font_size'] for b in blocks)
    max_font_blocks = [b for b in blocks if b['font_size'] == max_font]
    max_font_blocks.sort(key=lambda b: (b['y0'], b['page']))

    anchor_block = max_font_blocks[0]
    title_page = anchor_block['page']
    anchor_y = anchor_block['y0']

    title_blocks = [
        b for b in blocks
        if b['page'] == title_page and b['y0'] >= anchor_y and (1 * max_font <= b['font_size'] <= 2.0 * max_font)
    ]
    title_blocks.sort(key=lambda b: b['y0'])
    title_lines = [b['text'] for b in title_blocks]
    title_text = deduplicate(' '.join(title_lines))

    filtered_blocks = [
        b for b in blocks
        if (b['page'] > title_page) or (b['page'] == title_page and b['y0'] > anchor_y)
    ]
    return title_text, filtered_blocks


def cluster_font_sizes(blocks):
    freq = Counter(round(b['font_size']) for b in blocks)
    body = freq.most_common(1)[0][0]
    heads = sorted([s for s in freq if s > body], reverse=True)[:4]
    return heads, body


def deduplicate_lines(blocks):
    result = []
    seen = []
    for block in blocks:
        duplicate_found = False
        for existing in seen:
            if block['page'] == existing['page'] and abs(block['y0'] - existing['y0']) < 2.0 and block['text'] == existing['text']:
                duplicate_found = True
                break
        if not duplicate_found:
            seen.append(block)
            result.append(block)
    return result


def classify_headings(blocks, title=""):
    heads, body = cluster_font_sizes(blocks)
    blocks = deduplicate_lines(blocks)
    items = []
    for b in blocks:
        s = round(b['font_size'])
        t = b['text']
        if not t:
            continue
        if sum(c.isalpha() for c in t) / max(len(t), 1) < 0.4:
            continue

        fixed_text = deduplicate(t)
        lvl = None

        if s in heads:
            lvl = 'H' + str(heads.index(s) + 1)
        elif s > body and b['bold'] and abs(b['x0'] - 150) < 50:
            lvl = 'H3'

        if lvl:
            items.append((b['page'], b['y0'], b['x0'], lvl, fixed_text))

    items.sort(key=lambda x: (x[0], x[1], x[2]))

    outline = []
    seen_h1 = False
    for pg, y, x, lvl, txt in items:
        if lvl == 'H1':
            seen_h1 = True
            outline.append({'level': lvl, 'text': txt, 'page': pg})
        elif lvl == 'H2' and seen_h1:
            outline.append({'level': lvl, 'text': txt, 'page': pg})
        elif lvl == 'H3' and seen_h1:
            outline.append({'level': lvl, 'text': txt, 'page': pg})

    return outline


def extract_outline(path):
    doc = fitz.open(path)
    chars = extract_characters(doc)
    chars = deduplicate_chars(chars)

    temp = {}
    for c in chars:
        key = (c['page'], round(c['y0'], 1))
        temp.setdefault(key, []).append(c)

    blocks = []
    for (pg, y), line_chars in temp.items():
        line_chars.sort(key=lambda x: x['x0'])
        text = ''.join([x['char'] for x in line_chars])
        font_size = max(x['font_size'] for x in line_chars)
        bold = any(x['bold'] for x in line_chars)
        x0 = min(x['x0'] for x in line_chars)
        blocks.append({
            'text': text,
            'font_size': font_size,
            'bold': bold,
            'page': pg,
            'x0': x0,
            'y0': y
        })

    title, remaining_blocks = detect_title_and_filter_blocks(blocks)
    outline = classify_headings(remaining_blocks, title)
    return {'title': title, 'outline': outline}


def main(inp, outp):
    inp, outp = Path(inp), Path(outp)
    outp.mkdir(exist_ok=True)
    for pdf in inp.glob('*.pdf'):
        print(f"Processing {pdf.name}...")
        result = extract_outline(pdf)
        with open(outp / f'{pdf.stem}.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  -> Completed {pdf.name}\n")
    print("All files processed.")


if __name__ == '__main__':
    import sys
    input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/app/input")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/app/output")
    if len(sys.argv) != 3:
        print('Usage: process_pdfs.py <input_dir> <output_dir>')
        sys.exit(1)
    main(input_dir, output_dir)

import fitz  # PyMuPDF
import json
from pathlib import Path
from collections import defaultdict, Counter
import sys

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

                        chars.append({
                            "char": c,
                            "font_size": round(font_size, 1),
                            "bold": bold,
                            "page": page_num,
                            "x0": round(cx0, 2),
                            "x1": round(cx1, 2),
                            "y0": round(cy0, 2),
                            "y1": round(cy1, 2),
                        })
    return chars

def deduplicate_chars(chars):
    result = []
    seen_boxes = []
    for c in chars:
        padded_box = (
            round(c['x0'] - 0.3 * (c['x1'] - c['x0']), 1),
            round(c['y0'] - 0.3 * (c['y1'] - c['y0']), 1),
            round(c['x1'] + 0.3 * (c['x1'] - c['x0']), 1),
            round(c['y1'] + 0.3 * (c['y1'] - c['y0']), 1)
        )
        is_duplicate = any(
            abs(padded_box[0] - b[0]) < 0.5 and
            abs(padded_box[1] - b[1]) < 0.5 and
            abs(padded_box[2] - b[2]) < 0.5 and
            abs(padded_box[3] - b[3]) < 0.5
            for b in seen_boxes
        )
        if not is_duplicate:
            seen_boxes.append(padded_box)
            result.append(c)
    return result

def extract_outline(path):
    doc = fitz.open(path)
    chars = extract_characters(doc)
    chars = deduplicate_chars(chars)

    lines_by_y = defaultdict(list)
    for c in chars:
        lines_by_y[(c['page'], round(c['y0'], 1))].append(c)

    blocks = []
    for (pg, y), line_chars in lines_by_y.items():
        line_chars.sort(key=lambda x: x['x0'])
        text = ''.join([x['char'] for x in line_chars])
        font_sizes = [x['font_size'] for x in line_chars]
        base_font_size = max(set(font_sizes), key=font_sizes.count)
        similar_sizes = [fs for fs in font_sizes if abs(fs - base_font_size) <= 0.3 * base_font_size]
        font_size = max(similar_sizes) if similar_sizes else base_font_size
        bold = any(x['bold'] for x in line_chars)
        x0 = min(x['x0'] for x in line_chars)
        blocks.append({
            'text': text,
            'font_size': round(font_size, 1),
            'bold': bold,
            'page': pg,
            'x0': x0,
            'y0': y
        })

    max_font = max(b['font_size'] for b in blocks)
    max_font_blocks = [b for b in blocks if b['font_size'] == max_font]
    max_font_blocks.sort(key=lambda b: (b['y0'], b['page']))

    anchor_block = max_font_blocks[0]
    title_page = anchor_block['page']
    anchor_y = anchor_block['y0']

    title_blocks = [b for b in blocks if b['page'] == title_page and b['y0'] >= anchor_y and 1.0 * max_font <= b['font_size'] <= 2.0 * max_font]
    title_blocks.sort(key=lambda b: b['y0'])
    title_text = ' '.join(b['text'] for b in title_blocks)

    filtered_blocks = [b for b in blocks if (b['page'] > title_page) or (b['page'] == title_page and b['y0'] > anchor_y)]

    font_stats = Counter(round(b['font_size']) for b in filtered_blocks)
    body_font = font_stats.most_common(1)[0][0]
    heading_fonts = sorted([fs for fs in font_stats if fs > body_font], reverse=True)

    headings = []
    for b in filtered_blocks:
        if b['font_size'] in heading_fonts:
            level = 'H' + str(heading_fonts.index(b['font_size']) + 1)
            headings.append({'level': level, 'text': b['text'], 'page': b['page']})

    headings.sort(key=lambda h: (h['page'], next(b['y0'] for b in filtered_blocks if b['text'] == h['text'])))

    return {"title": title_text.strip(), "outline": headings}

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
    input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/app/input")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/app/output")
    if len(sys.argv) != 3:
        print('Usage: process_pdfs.py <input_dir> <output_dir>')
        sys.exit(1)
    main(input_dir, output_dir)

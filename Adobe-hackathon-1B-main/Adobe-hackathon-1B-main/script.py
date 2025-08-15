import fitz  # PyMuPDF
import json
import os
from pathlib import Path
import spacy
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from datetime import datetime
from collections import Counter
from difflib import SequenceMatcher
import re

# Load spaCy model
nlp = spacy.load("en_core_web_md")

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
    return deduplicate(candidates[0]['text']) if candidates else ""

def is_similar(a, b, threshold=0.85):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold

def cluster_font_sizes(blocks):
    freq = Counter(round(b['font_size']) for b in blocks)
    body = freq.most_common(1)[0][0]
    heads = sorted([s for s in freq if s > body], reverse=True)[:4]
    return heads, body

def mark_headings(blocks, title=""):
    heads, body = cluster_font_sizes(blocks)
    for b in blocks:
        s = round(b['font_size'])
        t = b['text']
        if not t or is_similar(t, title):
            b['is_heading'] = False
            continue
        if sum(c.isalpha() for c in t) / max(len(t), 1) < 0.4:
            b['is_heading'] = False
            continue
        is_numbered = re.match(r'^(\d+\.\d*|[IVXLCDM]+\.|[A-Z]\.)\s+', t)
        if s in heads:
            lvl = 'H' + str(heads.index(s) + 1)
            if lvl == 'H1' and is_numbered:
                lvl = 'H2'
            b['is_heading'] = True
            b['level'] = lvl
        elif s > body and b['bold'] and abs(b['x0'] - 150) < 50:
            b['is_heading'] = True
            b['level'] = 'H3'
        else:
            b['is_heading'] = False

def extract_sections(pdf_path):
    doc = fitz.open(pdf_path)
    blocks = extract_blocks(doc)
    title = detect_title(blocks)
    mark_headings(blocks, title)
    all_items = []
    for b in blocks:
        if b.get('is_heading', False):
            all_items.append({
                'type': 'heading',
                'page': b['page'],
                'y': b['y0'],
                'text': b['text'],
                'level': b['level']
            })
        else:
            all_items.append({
                'type': 'text',
                'page': b['page'],
                'y': b['y0'],
                'text': b['text']
            })
    all_items.sort(key=lambda x: (x['page'], -x['y']))
    sections = []
    current_section = None
    for item in all_items:
        if item['type'] == 'heading':
            if current_section is not None:
                sections.append(current_section)
            current_section = {
                'title': item['text'],
                'page': item['page'],
                'content': []  # list of (page, text)
            }
        else:
            if current_section is not None:
                current_section['content'].append((item['page'], item['text']))
    if current_section is not None:
        sections.append(current_section)
    sections = [sec for sec in sections if sec['content']]
    for sec in sections:
        sec['text'] = ' '.join([text for page, text in sec['content']])
    return sections, {'title': title, 'outline': [{'level': b['level'], 'text': b['text'], 'page': b['page']} for b in blocks if b.get('is_heading', False)]}

def compute_embeddings(texts):
    return [nlp(text).vector for text in texts]

def rank_sections_by_relevance(query, sections, top_k=5):
    if not sections:
        return []
    section_texts = [sec['text'] for sec in sections]
    section_vecs = compute_embeddings(section_texts)
    query_vec = nlp(query).vector.reshape(1, -1)
    if not section_vecs:
        print("[ERROR] No section vectors available for similarity check.")
        return []
    try:
        sims = cosine_similarity(query_vec, section_vecs)[0]
    except Exception as e:
        print(f"[ERROR] Cosine similarity failed: {e}")
        return []
    ranked = sorted(zip(sims, sections), key=lambda x: x[0], reverse=True)
    return ranked[:top_k]

def main(pdf_dir, input_json_path, output_json_path, outline_dir="outlines"):
    # Load input JSON
    with open(input_json_path, "r", encoding="utf-8") as f:
        input_data = json.load(f)
    
    documents = input_data["documents"]
    query = input_data["job_to_be_done"]["task"]
    
    # Create outline directory
    os.makedirs(outline_dir, exist_ok=True)
    
    # Extract sections and generate outline JSONs
    all_sections = []
    for doc in documents:
        pdf_path = os.path.join(pdf_dir, doc["filename"])
        if not os.path.exists(pdf_path):
            print(f"[WARNING] File not found: {pdf_path}")
            continue
        sections, outline = extract_sections(pdf_path)
        for sec in sections:
            sec['document'] = doc["filename"]
        all_sections.extend(sections)
        # Save outline JSON
        outline_path = os.path.join(outline_dir, f"{Path(doc['filename']).stem}.json")
        with open(outline_path, 'w', encoding='utf-8') as f:
            json.dump(outline, f, indent=2, ensure_ascii=False)
        print(f"[INFO] Outline saved to {outline_path}")
    
    if not all_sections:
        print("[ERROR] No sections extracted from any PDFs. Exiting.")
        return
    
    # Rank sections
    ranked = rank_sections_by_relevance(query, all_sections)
    
    # Prepare extracted_sections
    extracted_sections = [
        {
            "document": sec['document'],
            "section_title": sec['title'],
            "importance_rank": rank + 1,
            "page_number": sec['page']
        }
        for rank, (score, sec) in enumerate(ranked)
    ]
    
    # Prepare subsection_analysis
    subsection_analysis = []
    for score, sec in ranked:
        if sec['content']:
            line_texts = [text for page, text in sec['content']]
            line_vecs = compute_embeddings(line_texts)
            query_vec = nlp(query).vector.reshape(1, -1)
            line_sims = cosine_similarity(query_vec, line_vecs)[0]
            if line_sims.size > 0:
                best_line_idx = np.argmax(line_sims)
                best_line_page, best_line_text = sec['content'][best_line_idx]
                subsection_analysis.append({
                    "document": sec['document'],
                    "refined_text": best_line_text,
                    "page_number": best_line_page
                })
    
    # Construct output
    output = {
        "metadata": {
            "input_documents": [doc["filename"] for doc in documents],
            "persona": input_data["persona"]["role"],
            "job_to_be_done": input_data["job_to_be_done"]["task"],
            "processing_timestamp": datetime.now().isoformat()
        },
        "extracted_sections": extracted_sections,
        "subsection_analysis": subsection_analysis
    }
    
    # Save final output
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[✅] Final output written to {output_json_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 4:
        print("Usage: python script.py <pdf_folder> <input_json> <output_json>")
        sys.exit(1)
    pdf_dir = sys.argv[1]
    input_json_path = sys.argv[2]
    output_json_path = sys.argv[3]
    main(pdf_dir, input_json_path, output_json_path)
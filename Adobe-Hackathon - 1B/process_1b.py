import sys
import json
import time
import fitz  # PyMuPDF
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer, util

def extract_sections(pdf_path):
    doc = fitz.open(pdf_path)
    sections = []
    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if "lines" not in b:
                continue
            lines = []
            for line in b["lines"]:
                text = "".join(span.get("text","") for span in line.get("spans",[]))
                if text.strip(): lines.append(text.strip())
            title = " ".join(lines).strip()
            if title and len(title.split()) < 12:
                content = page.get_text()
                sections.append({
                    'title': title,
                    'page': page_num,
                    'content': content,
                    'document': Path(pdf_path).name
                })
    return sections

def rank_sections(sections, query, model, top_k=5):
    titles = [s['title'] for s in sections]
    embeddings = model.encode(titles, convert_to_tensor=True)
    q_emb = model.encode(query, convert_to_tensor=True)
    scores = util.cos_sim(q_emb, embeddings)[0].cpu().numpy()
    idxs = np.argsort(-scores)[:top_k]
    ranked = []
    for i, idx in enumerate(idxs, start=1):
        sec = sections[int(idx)]
        ranked.append({
            'document': sec['document'],
            'page': sec['page'],
            'section_title': sec['title'],
            'importance_rank': i,
            'content': sec['content']
        })
    return ranked

def extract_subsections(model, query, top_sections, max_snippets=3):
    snippets = []
    q_emb = model.encode(query, convert_to_tensor=True)
    for sec in top_sections:
        sents = [s.strip() for s in sec['content'].split('.') if s.strip()]
        if not sents: continue
        sent_embs = model.encode(sents, convert_to_tensor=True)
        scores = util.cos_sim(q_emb, sent_embs)[0].cpu().numpy()
        for idx in np.argsort(-scores)[:max_snippets]:
            snippets.append({
                'document': sec['document'],
                'page': sec['page'],
                'refined_text': sents[int(idx)]
            })
    return snippets

def unwrap_persona(raw):
    if 'persona' in raw and isinstance(raw['persona'], dict):
        role = raw['persona'].get('role') or next(iter(raw['persona'].values()))
    else:
        role = raw.get('role') or raw.get('persona')
    job = raw.get('job') or raw.get('task') or raw.get('job_to_be_done') or raw.get('todo')
    return role, job

def main(input_dir, persona_file, output_dir):
    inp = Path(input_dir)
    outp = Path(output_dir); outp.mkdir(exist_ok=True)

    raw = json.loads(Path(persona_file).read_text())
    role, job = unwrap_persona(raw)
    if not role or not job:
        print("Error: Could not extract role/job")
        sys.exit(1)
    query = f"{role}. {job}"

    model = SentenceTransformer('all-MiniLM-L6-v2')
    start = time.time()
    results = {
        'metadata': {
            'input_documents': [p.name for p in inp.glob('*.pdf')],
            'persona': role,
            'job_to_be_done': job,
            'processing_time_seconds': None
        },
        'extracted_sections': [],
        'subsection_analysis': []
    }
    for pdf in inp.glob('*.pdf'):
        secs = extract_sections(pdf)
        ranked = rank_sections(secs, query, model)
        results['extracted_sections'].extend([{k:sec[k] for k in ['document','page','section_title','importance_rank']} for sec in ranked])
        snippets = extract_subsections(model, query, ranked)
        results['subsection_analysis'].extend(snippets)
    results['metadata']['processing_time_seconds'] = round(time.time() - start,2)
    out = outp / 'results.json'
    with open(out,'w',encoding='utf-8') as f: json.dump(results,f,ensure_ascii=False,indent=2)
    print(f"✅ Done in {results['metadata']['processing_time_seconds']}s. Out: {out}")

if __name__=='__main__':
    if len(sys.argv)!=4:
        print("Usage: python main.py <input_dir> <persona.json> <output_dir>")
        sys.exit(1)
    main(sys.argv[1],sys.argv[2],sys.argv[3])

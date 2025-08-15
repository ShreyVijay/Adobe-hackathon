# 📰 Multilingual PDF Heading Extractor

This project extracts **titles and headings** (H1, H2, H3) from PDF documents using [PyMuPDF](https://pymupdf.readthedocs.io/), supporting **multilingual heading detection** with customizable regex patterns (via `languages.json`).

---

## 🚀 Features

- Extracts document **title and structured headings**.
- Works for multiple languages using **language-specific heading patterns**.
- Detects headings using:
  - Font size and boldness
  - Indentation
  - Language-specific patterns (e.g. `Chapter`, `Capítulo`)
- Supports **batch processing** of PDFs from a directory.
- Fully containerized using **Docker**.

---

## 📁 Directory Structure

project/
├── input/ # Place input PDF files here
├── output/ # JSON output files will be saved here
├── process_pdfs.py # Main heading extraction script
├── languages.json # Language-specific heading patterns
├── requirements.txt # Python dependencies
└── Dockerfile # For containerization

yaml
Copy
Edit

---

## 🔧 Setup (Without Docker)

### 1. Install dependencies

```bash
pip install -r requirements.txt
2. Run the script
bash
Copy
Edit
python process_pdfs.py input output en
Replace en with language code like es for Spanish.

🐳 Using Docker (Recommended)
1. Build Docker Image
bash
Copy
Edit
docker build -t pdf-heading-extractor .
2. Run the container
a. Default (English)
bash
Copy
Edit
docker run --rm \
  -v "$(pwd)/input:/app/input" \
  -v "$(pwd)/output:/app/output" \
  pdf-heading-extractor
b. Spanish or other language
bash
Copy
Edit
docker run --rm \
  -v "$(pwd)/input:/app/input" \
  -v "$(pwd)/output:/app/output" \
  pdf-heading-extractor python process_pdfs.py /app/input /app/output es
🌐 Multilingual Support
You can define heading patterns for any language in the languages.json file.

Example: languages.json
json
Copy
Edit
{
  "en": {
    "heading_patterns": [
      "^(Chapter|CHAPTER|Section|SECTION|Part|PART)\\s+\\d+",
      "^\\d+(\\.\\d+)*\\s+[A-Z].*"
    ]
  },
  "es": {
    "heading_patterns": [
      "^(Cap[ií]tulo|SECCI[ÓO]N|Parte)\\s+\\d+",
      "^\\d+(\\.\\d+)*\\s+[A-ZÁÉÍÓÚÑ].*"
    ]
  }
}
🛠 Add more languages as needed.

📤 Output Format
Each output JSON will contain:

json
Copy
Edit
{
  "title": "Document Title",
  "outline": [
    { "level": "H1", "text": "Chapter 1 Introduction", "page": 1 },
    { "level": "H2", "text": "Section 1.1 Motivation", "page": 1 },
    { "level": "H3", "text": "Subsection", "page": 2 }
  ]
}
🧪 Test it
Place sample PDFs in the input/ folder.

Run the Docker or Python command.

Find .json files with extracted headings inside the output/ folder.


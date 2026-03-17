"""
Content Extraction — Extract text/data from files for intelligent routing.

Extracts content from:
- Images (OCR via Tesseract or Vision LLM)
- PDFs (text extraction)
- Documents (text files, markdown, etc.)
- Code files (syntax-aware)

Usage:
    from core.extraction import extract_content
    content = extract_content("/path/to/file.pdf")
"""

import logging
from pathlib import Path
from typing import Dict, Optional
import mimetypes

log = logging.getLogger("extraction")


def extract_text_from_pdf(file_path: Path) -> str:
    """Extract text from PDF using PyPDF2 or pdfplumber."""
    try:
        # Try pdfplumber first (better text extraction)
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return text.strip()
        except ImportError:
            pass

        # Fallback to PyPDF2
        try:
            import PyPDF2
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return text.strip()
        except ImportError:
            log.warning("Neither pdfplumber nor PyPDF2 installed. Install with: pip install pdfplumber")
            return ""

    except Exception as e:
        log.error(f"PDF extraction failed for {file_path}: {e}")
        return ""


def extract_text_from_image_ocr(file_path: Path) -> str:
    """Extract text from image using Tesseract OCR."""
    try:
        from PIL import Image
        import pytesseract
        import os
        # WSL: use Windows tesseract via interop; Linux: use system binary
        if os.path.exists("/mnt/c/Program Files/Tesseract-OCR/tesseract.exe"):
            pytesseract.pytesseract.tesseract_cmd = "/mnt/c/Program Files/Tesseract-OCR/tesseract.exe"

        image = Image.open(file_path)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except ImportError:
        log.warning("pytesseract or PIL not installed. Install with: pip install pytesseract pillow")
        log.warning("Also install Tesseract: https://github.com/tesseract-ocr/tesseract")
        return ""
    except Exception as e:
        log.error(f"OCR failed for {file_path}: {e}")
        return ""


def extract_text_from_image_vision(file_path: Path) -> str:
    """Extract text from image using Vision LLM (Gemini)."""
    try:
        import sys
        import base64
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core import llm_router

        # Load image as base64
        with open(file_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')

        # Use Gemini Vision to extract text
        prompt = """Extract all visible text from this image.

Output format:
- If the image contains readable text, output ONLY the extracted text
- If the image has no text, output: [NO TEXT]
- If the image has mixed content, extract all visible text

Do not add commentary, just output the text."""

        response = llm_router.ask_with_vision(
            prompt=prompt,
            image_data=image_data,
            preferred_tier="free"
        )

        if response and "[NO TEXT]" not in response:
            return response.strip()
        return ""

    except Exception as e:
        log.error(f"Vision LLM extraction failed for {file_path}: {e}")
        return ""


def extract_text_from_document(file_path: Path) -> str:
    """Extract text from text-based documents."""
    try:
        # Try reading as UTF-8
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # Try other encodings
        for encoding in ['latin-1', 'cp1252', 'utf-16']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except:
                continue
        log.warning(f"Could not decode {file_path} as text")
        return ""
    except Exception as e:
        log.error(f"Document extraction failed for {file_path}: {e}")
        return ""


def extract_content(file_path: str, use_vision_for_ocr: bool = False) -> Dict:
    """
    Extract content from a file based on its type.

    Args:
        file_path: Path to the file
        use_vision_for_ocr: If True, use Vision LLM instead of Tesseract for images

    Returns:
        {
            "text": str,           # Extracted text content
            "method": str,         # Extraction method used
            "success": bool,       # Whether extraction succeeded
            "error": str or None   # Error message if failed
        }
    """
    path = Path(file_path)

    if not path.exists():
        return {"text": "", "method": "none", "success": False, "error": "File not found"}

    # Determine file type
    mime_type, _ = mimetypes.guess_type(str(path))
    suffix = path.suffix.lower()

    # PDF files
    if suffix == '.pdf' or (mime_type and 'pdf' in mime_type):
        text = extract_text_from_pdf(path)
        return {
            "text": text,
            "method": "pdf_extraction",
            "success": bool(text),
            "error": None if text else "No text extracted"
        }

    # Image files
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
    if suffix in image_extensions or (mime_type and 'image' in mime_type):
        if use_vision_for_ocr:
            text = extract_text_from_image_vision(path)
            method = "vision_llm"
        else:
            text = extract_text_from_image_ocr(path)
            method = "tesseract_ocr"

        return {
            "text": text,
            "method": method,
            "success": bool(text),
            "error": None if text else "No text found in image"
        }

    # Text-based files
    text_extensions = {
        '.txt', '.md', '.markdown', '.rst', '.log',
        '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.c', '.cpp', '.h',
        '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg',
        '.html', '.css', '.scss', '.sass',
        '.sh', '.bash', '.zsh', '.fish',
        '.rs', '.go', '.rb', '.php', '.swift', '.kt'
    }

    if suffix in text_extensions or (mime_type and 'text' in mime_type):
        text = extract_text_from_document(path)
        return {
            "text": text,
            "method": "text_read",
            "success": bool(text),
            "error": None if text else "No text extracted"
        }

    # Unknown file type
    return {
        "text": "",
        "method": "none",
        "success": False,
        "error": f"Unsupported file type: {suffix}"
    }


def analyze_content_for_routing(content: str, filename: str, file_type: str) -> Dict:
    """
    Use LLM to analyze content and suggest routing destination.

    Args:
        content: Extracted text content
        filename: Original filename
        file_type: File type/extension

    Returns:
        {
            "suggested_destination": str,  # Suggested node/destination
            "confidence": float,            # 0-1 confidence score
            "reasoning": str,               # Why this destination
            "keywords": List[str]           # Extracted keywords
        }
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core import llm_router

        # Truncate content if too long (max ~2000 chars for analysis)
        content_preview = content[:2000] + ("..." if len(content) > 2000 else "")

        prompt = f"""Analyze this file and suggest the best routing destination.

Filename: {filename}
File Type: {file_type}

Content Preview:
{content_preview}

Available Destinations:
- code: Programming code, scripts, technical files
- documents: Written documents, notes, reports, articles
- screenshots: Screenshots, screen captures
- images: Photos, diagrams, visual content
- media: Audio/video files
- data: Datasets, CSVs, JSON data files
- personal: Personal notes, journal entries, private content
- work: Work-related content, professional documents
- reference: Reference materials, documentation, guides
- archive: Old/historical content to be archived
- unknown: Cannot determine appropriate destination

Respond in this exact JSON format:
{{
  "destination": "category_name",
  "confidence": 0.95,
  "reasoning": "Brief explanation",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}}"""

        response = llm_router.ask(prompt, preferred_tier="free")

        if not response or not response.content:
            return {
                "suggested_destination": "unknown",
                "confidence": 0.0,
                "reasoning": "Fleet unavailable",
                "keywords": []
            }

        # Parse JSON response
        import json
        import re

        # Try to extract JSON from response
        json_match = re.search(r'\{[^}]+\}', response.content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return {
                "suggested_destination": result.get("destination", "unknown"),
                "confidence": float(result.get("confidence", 0.5)),
                "reasoning": result.get("reasoning", ""),
                "keywords": result.get("keywords", [])
            }

        # Fallback if JSON parsing fails
        return {
            "suggested_destination": "unknown",
            "confidence": 0.3,
            "reasoning": "Could not parse LLM response",
            "keywords": []
        }

    except Exception as e:
        log.error(f"LLM routing analysis failed: {e}")
        return {
            "suggested_destination": "unknown",
            "confidence": 0.0,
            "reasoning": f"Error: {str(e)}",
            "keywords": []
        }


if __name__ == "__main__":
    # CLI testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python extraction.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]

    print(f"Extracting content from: {file_path}")
    print("-" * 50)

    result = extract_content(file_path)

    print(f"Method: {result['method']}")
    print(f"Success: {result['success']}")
    if result['error']:
        print(f"Error: {result['error']}")

    if result['text']:
        print(f"\nExtracted Text ({len(result['text'])} chars):")
        print("-" * 50)
        print(result['text'][:500])
        if len(result['text']) > 500:
            print("...")

        # Analyze for routing
        print("\n" + "=" * 50)
        print("LLM Routing Analysis:")
        print("=" * 50)

        analysis = analyze_content_for_routing(
            result['text'],
            Path(file_path).name,
            Path(file_path).suffix
        )

        print(f"Suggested Destination: {analysis['suggested_destination']}")
        print(f"Confidence: {analysis['confidence']:.0%}")
        print(f"Reasoning: {analysis['reasoning']}")
        print(f"Keywords: {', '.join(analysis['keywords'])}")

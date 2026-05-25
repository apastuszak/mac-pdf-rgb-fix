# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the tools

```bash
# GUI
python3 mac_pdf_rgb_fix_gui.py

# CLI
python3 pdf_images_to_rgb.py input.pdf [output.pdf] [--quality N] [--no-metadata]

# Install dependencies
pip install pymupdf pillow --break-system-packages
# If tkinter is missing:
brew install python-tk
```

## Architecture

Two entry points that share core conversion logic:

**`pdf_images_to_rgb.py`** — CLI and importable library. Key functions:

- `process_pdf(input, output, jpeg_quality, prompt_for_metadata, metadata)` — main pipeline
- `process_pdf_with_metadata(input, output, jpeg_quality, metadata)` — GUI-facing wrapper; passes a pre-built metadata dict instead of prompting interactively
- `needs_conversion(colorspace, filter_)` — returns True for CMYK, grayscale, or JPX images
- `get_rgb_pixmap(doc, xref)` — decodes any image to an RGB `fitz.Pixmap` via PyMuPDF's LCMS pipeline
- `encode_jpeg(pix, quality)` — encodes a Pixmap to JPEG bytes via Pillow

**`mac_pdf_rgb_fix_gui.py`** — ~14,800-line file. The first ~14,400 lines are base64-encoded embedded font data (Source Sans 3). Actual GUI code starts around line 14,410. Single `App(tk.Tk)` class; `_build_ui()` constructs all widgets; `_run_conversion()` runs in a background `threading.Thread` and posts results back via `self.after(0, ...)`.

The GUI imports `process_pdf_with_metadata` from `pdf_images_to_rgb` inside `_run_conversion()` (not at module level) to avoid import-time side effects.

## Critical constraints

- **CMYK conversion must use PyMuPDF's LCMS** (`fitz.Pixmap(fitz.csRGB, pix)`). Pillow's CMYK→RGB produces a green colour cast.
- **`deflate_images` must stay `False`** on `doc.save()`. If enabled, PyMuPDF re-compresses JPEG streams as FlateDecode, undoing the encoding work.
- **Shared XObjects are processed once by xref**, not once per page. Modifying a shared object updates it everywhere it's referenced.
- **`/Mask` vs `/SMask` must be preserved exactly.** PyMuPDF's `get_images()` reports both stencil masks (`/Mask`, 1-bit) and soft masks (`/SMask`, 8-bit grayscale) under the same `smask` field. Always check `doc.xref_get_key(xref, "Mask")` on the original object to determine which key to write. Writing `/SMask` for a stencil mask corrupts transparency compositing and can cause unrelated images elsewhere on the page to disappear.
- **Indexed/palette images use FlateDecode (lossless)**, not JPEG — JPEG degrades their sharp edges.

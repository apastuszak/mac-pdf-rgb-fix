# mac-pdf-rgb-fix

A Python utility that fixes PDF files that display broken, missing, or incorrectly coloured images on Apple devices (macOS, iOS, iPadOS).

Available as both a command-line script and a graphical user interface.

## The Problem

PDFs produced by professional print workflows — InDesign exports, publisher-supplied ebooks, scanned documents — commonly contain images in two formats that Apple's PDF renderer handles poorly:

- **CMYK colour space** — the four-ink model used in print (Cyan, Magenta, Yellow, Black). Apple's renderer often displays CMYK images with wrong colours or skips them entirely.
- **JPEG 2000 (JPX) compression** — a successor to standard JPEG used in some PDF workflows. Apple's PDF renderer has inconsistent JPX support, especially combined with CMYK.

The combination of CMYK + JPX is particularly common in some gaming and hobby PDFs (RPG books, wargame rules, etc.) and is essentially guaranteed to produce broken images on Apple platforms.

To be clear, this a bug in Apple's PDFKit rendering image, and not the fault of the publishers making and selling these PDFs. This script is a workaround to allow these PDFs to work on Apple devices until Apple gets around to fixing this issue.

## The Solution

Both tools convert all affected images to standard RGB colour space and re-encode them as JPEG — a format Apple handles correctly. Transparency (SMask) information is preserved. Images that are already RGB and not JPX-encoded are left untouched.

## Files

| File | Description |
|------|-------------|
| `pdf_images_to_rgb.py` | Command-line script |
| `mac_pdf_rgb_fix_gui.py` | Graphical user interface |

## Requirements

Python 3.10+ and two packages:

```bash
pip install pymupdf pillow
```

On Homebrew-managed Python installs (common on macOS), you may need:

```bash
pip install pymupdf pillow --break-system-packages
```

The GUI also requires Tkinter, which ships with Python but may need a separate install on some macOS setups:

```bash
brew install python-tk
```

## Usage

### GUI

```bash
python mac_pdf_rgb_fix_gui.py
# If that doesn't work, try:
python3 mac_pdf_rgb_fix_gui.py
```

Use the Browse buttons to select input and output files, adjust the quality slider, fill in any metadata, and click Convert PDF. Progress is shown in the log panel.

### Command Line

```bash
# Basic usage — output saved as input_rgb.pdf
python pdf_images_to_rgb.py input.pdf

# Specify output path
python pdf_images_to_rgb.py input.pdf output.pdf

# Set JPEG quality (1–95, default 95)
python pdf_images_to_rgb.py input.pdf output.pdf --quality 85

# Skip metadata prompts (useful for batch/scripted use)
python pdf_images_to_rgb.py input.pdf output.pdf --no-metadata
```

> **Note:** On macOS, `python` may not be available. If you get a "command not found" error, use `python3` instead throughout.

After processing, the command-line script will prompt you to enter PDF metadata (Title, Author, Subject, Keywords). Press Enter to keep any existing values. Use `--no-metadata` to skip this step for batch processing.

## Quality and File Size

The default quality of 95 produces output that is visually indistinguishable from the original. Note that the source images in print PDFs are typically already lossy-compressed (often at JPX quality 75), so q=95 JPEG output is actually *higher* quality than the originals.

Approximate output sizes for a typical 100-page illustrated PDF:

| Quality | Approx. size |
|---------|-------------|
| 75      | ~60% of original |
| 85      | ~75% of original |
| 95      | ~110% of original |

## Technical Details

- Uses [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF manipulation and colour conversion
- CMYK→RGB conversion uses PyMuPDF's internal colour management pipeline (LCMS), which correctly handles Adobe-style CMYK encoding — naive mathematical conversion (as used by Pillow) produces a green colour cast
- Shared XObjects (images referenced by multiple pages) are processed once and updated in place, so the fix correctly propagates to all pages
- SMask objects (transparency masks) are preserved; their xref numbers are carried forward into the new image dictionaries
- Indexed/palette images are kept lossless (FlateDecode) since JPEG compression would degrade their sharp edges
- PyMuPDF's `deflate_images` is deliberately left disabled on save to prevent re-compression of JPEG streams as FlateDecode

## Fonts

The GUI embeds [Source Sans 3](https://github.com/adobe-fonts/source-sans) by Adobe, released under the [SIL Open Font License 1.1](https://scripts.sil.org/OFL). The OFL is compatible with the GPL v3 license covering this application's code. The fonts are embedded for convenience and are not sold as a standalone product.

## Attribution

This project was entirely vibe coded using [Claude](https://claude.ai) by Anthropic.

## License

[GNU General Public License v3.0](LICENSE)
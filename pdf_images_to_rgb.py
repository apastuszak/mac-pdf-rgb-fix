#!/usr/bin/env python3
# mac-pdf-rgb-fix — Fix CMYK/JPX images in PDFs for Apple device compatibility
# Copyright (C) 2025 Andy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Convert all images in a PDF to RGB color space, re-encoding CMYK, grayscale,
and JPEG 2000 (JPX) images for full compatibility with Apple's PDF renderer
on macOS and iOS/iPadOS.

Background: PDFs from professional print workflows often contain CMYK images
(the 4-color ink model used in printing) and/or JPEG 2000 (JPX) compressed
images. Apple's PDF renderer handles neither well, causing images to appear
missing or with wrong colors. This script converts everything to standard
RGB JPEG, which Apple handles correctly.

Photographic images are re-encoded as JPEG (default quality 95).
Indexed/palette images (e.g. pixel art, diagrams) are kept lossless.

Uses PyMuPDF (fitz) for accurate CMYK→RGB color conversion via its built-in
color management pipeline, which correctly handles Adobe-style CMYK encoding.

Usage:
    python pdf_images_to_rgb.py input.pdf [output.pdf] [--quality N]

If output path is not specified, the result is saved as input_rgb.pdf.
Quality defaults to 95 (range 1-95). Higher = larger file, better quality.

Requirements:
    pip install pymupdf pillow --break-system-packages
"""

import sys
import io
import os
import tempfile
from pathlib import Path
import fitz          # PyMuPDF — PDF manipulation and color conversion
from PIL import Image  # Pillow — JPEG encoding


# PDF stream filter name for JPEG 2000 encoding
JPX_FILTER = "JPXDecode"

# Default JPEG output quality (95 = high quality, visually near-lossless)
DEFAULT_QUALITY = 95

# These colorspaces indicate palette/indexed images (e.g. diagrams, pixel art).
# They should stay lossless since JPEG would destroy their sharp edges.
LOSSLESS_COLORSPACES = {"Indexed"}


def needs_conversion(cs: str, filter_: str) -> bool:
    """
    Determine whether an image needs to be re-encoded.

    Returns True if:
    - The colorspace is not RGB (e.g. CMYK, grayscale, Indexed) — Apple
      can't reliably render non-RGB images in PDFs.
    - The image is JPEG 2000 (JPX) encoded — even RGB JPX images fail
      to render on macOS/iOS in many cases.
    """
    if cs not in ("DeviceRGB", "sRGB"):
        return True
    if JPX_FILTER in (filter_ or ""):
        return True
    return False


def get_rgb_pixmap(doc: fitz.Document, xref: int) -> fitz.Pixmap | None:
    """
    Decode an image from the PDF and return it as an RGB Pixmap.

    Uses PyMuPDF's internal color management pipeline, which correctly
    handles Adobe-style CMYK encoding (where channel values are inverted
    compared to standard CMYK). Plain Pillow conversion gets this wrong
    and produces a green tint.

    xref is the PDF cross-reference number identifying the image object.
    Returns None if conversion fails.

    Note: we do NOT strip alpha here. Transparency in PDF images is handled
    via a separate SMask (soft mask) object referenced from the image dict,
    not embedded alpha — so there's nothing to strip.
    """
    try:
        # Load the raw image data from the PDF into a Pixmap
        pix = fitz.Pixmap(doc, xref)

        # If not already 3-channel RGB (n==3), convert to RGB.
        # This handles CMYK (n=4), grayscale (n=1), and other colorspaces.
        if pix.colorspace and pix.colorspace.n != 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)

        return pix
    except Exception as e:
        print(f"    Warning: Pixmap conversion failed — {e}")
        return None


def encode_jpeg(pix: fitz.Pixmap, quality: int) -> bytes:
    """
    Encode a PyMuPDF Pixmap as a JPEG byte string.

    Pillow is used for JPEG encoding since PyMuPDF doesn't expose
    a direct JPEG encoder for arbitrary pixmaps.
    optimize=True enables Huffman table optimization for slightly smaller files.
    """
    # Convert PyMuPDF's raw sample bytes into a Pillow Image
    img = Image.frombytes("RGB", (pix.width, pix.height), bytes(pix.samples))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()



def prompt_metadata(existing: dict) -> dict:
    """
    Interactively prompt for PDF metadata fields.
    Pressing Enter without typing anything keeps the existing value.
    Returns a metadata dict suitable for passing to doc.set_metadata().
    """
    print("Enter PDF metadata (press Enter to keep existing value):\n")

    def ask(label: str, key: str) -> str:
        current = existing.get(key, "")
        display = f" [{current}]" if current else ""
        value = input(f"  {label}{display}: ").strip()
        return value if value else current

    return {
        "title":    ask("Title", "title"),
        "author":   ask("Author", "author"),
        "subject":  ask("Subject", "subject"),
        "keywords": ask("Keywords", "keywords"),
        "creator":  existing.get("creator", ""),
        "producer": existing.get("producer", ""),
    }


def _repair_xref(input_path: str) -> str | None:
    """
    Repair a PDF's xref table using pikepdf (QPDF backend) and return the path
    to a temporary repaired file.

    Some PDFs from print workflows store objects in non-standard locations that
    PyMuPDF/MuPDF cannot find via the xref table, emitting "cannot find object
    in xref" errors and silently dropping those objects on save. pikepdf/QPDF
    scans the entire file for objects and rebuilds a clean xref, so PyMuPDF can
    then load and save them correctly.

    Returns a temp file path (caller must delete it), or None if pikepdf is not
    installed or repair fails.
    """
    try:
        import pikepdf
    except ImportError:
        return None

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)
    try:
        with pikepdf.open(input_path) as pdf:
            pdf.save(tmp_path)
        return tmp_path
    except Exception as e:
        print(f"  Warning: pikepdf xref repair failed — {e}")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return None


def process_pdf_with_metadata(input_path: str, output_path: str, jpeg_quality: int, metadata: dict) -> None:
    """Wrapper for use by the GUI: applies a pre-built metadata dict instead of prompting."""
    process_pdf(input_path, output_path, jpeg_quality, prompt_for_metadata=False, metadata=metadata)


def process_pdf(input_path: str, output_path: str, jpeg_quality: int, prompt_for_metadata: bool = True, metadata: dict = None) -> None:
    """
    Main processing function. Opens the PDF, finds all image XObjects,
    converts those that need it, and saves the result.
    """
    # Some PDFs have objects that are physically present in the file but absent
    # from the xref table (MuPDF prints "cannot find object in xref" for these).
    # MuPDF can render them but drops them on save. pikepdf/QPDF recovers them
    # by scanning the whole file, so we repair first if pikepdf is available.
    repaired_path = _repair_xref(input_path)
    if repaired_path:
        print("  Note: repaired PDF xref via pikepdf — processing repaired copy")
        load_path = repaired_path
    else:
        load_path = input_path

    doc = fitz.open(load_path)

    total_converted = 0
    total_skipped = 0

    # --- Collect all unique image XObjects across all pages ---
    #
    # PDF images are stored as XObjects (cross-reference objects) that can be
    # shared across multiple pages — e.g. a repeated background image on every
    # page is stored once and referenced many times. We deduplicate by xref so
    # we only process each unique image once, which is both faster and correct
    # (modifying a shared object once updates it everywhere it's referenced).
    seen_xrefs = set()
    image_xrefs = []
    for page in doc:
        for img in page.get_images(full=True):
            xref = img[0]
            if xref not in seen_xrefs:
                seen_xrefs.add(xref)
                image_xrefs.append((page.number + 1, xref, img))

    print(f"Found {len(image_xrefs)} unique image XObjects across {len(doc)} pages.")
    print(f"JPEG quality: {jpeg_quality}\n")

    # --- Process each unique image ---
    for page_num, xref, img in image_xrefs:
        # Unpack image metadata from PyMuPDF's get_images() tuple.
        # smask is the xref of the SMask (soft mask / transparency mask) object,
        # or 0 if there is none.
        _, smask, w, h, bpc, colorspace, _, name, filter_, _ = img[:10]

        print(f"  Page {page_num} | xref={xref} name={name} | {w}x{h} | cs={colorspace} filter={filter_}")

        if not needs_conversion(colorspace, filter_):
            print(f"    Skipped (already RGB, non-JPX)")
            total_skipped += 1
            continue

        # Build a human-readable reason string for the log output
        reason_parts = []
        if colorspace not in ("DeviceRGB", "sRGB"):
            reason_parts.append(colorspace)
        if JPX_FILTER in (filter_ or ""):
            reason_parts.append("JPX")

        # Decode and convert the image to an RGB Pixmap
        pix = get_rgb_pixmap(doc, xref)
        if pix is None:
            total_skipped += 1
            continue

        # Indexed (palette) images get lossless FlateDecode; everything else gets JPEG
        use_lossless = colorspace in LOSSLESS_COLORSPACES
        encoding = "FlateDecode (lossless)" if use_lossless else f"JPEG q={jpeg_quality}"
        print(f"    Converting ({', '.join(reason_parts)}) → RGB {encoding}")

        # Build the mask entry for the object dict.
        # PyMuPDF's get_images() reports both /Mask (1-bit stencil) and /SMask
        # (8-bit soft mask) under the same "smask" field. We must check the original
        # dict to preserve the correct key — writing /SMask for a stencil mask
        # corrupts the transparency compositing and can cause unrelated images on
        # the same page to disappear.
        if smask:
            mask_key = "SMask"
            try:
                if doc.xref_get_key(xref, "Mask")[0] != "null":
                    mask_key = "Mask"
            except Exception:
                pass
            smask_entry = f"  /{mask_key} {smask} 0 R\n"
        else:
            smask_entry = ""

        if use_lossless:
            # For lossless: write raw pixel bytes and let PyMuPDF compress them.
            # We omit /Filter from the dict here — update_stream(compress=True)
            # adds /Filter /FlateDecode and /Length automatically.
            new_obj_def = (
                f"<<\n"
                f"  /Type /XObject /Subtype /Image\n"
                f"  /Width {pix.width} /Height {pix.height}\n"
                f"  /ColorSpace /DeviceRGB /BitsPerComponent 8\n"
                f"{smask_entry}"
                f">>"
            )
            doc.update_object(xref, new_obj_def)
            doc.update_stream(xref, bytes(pix.samples), compress=True)

        else:
            # For JPEG: encode the image ourselves, then embed the raw JPEG bytes.
            jpeg_bytes = encode_jpeg(pix, jpeg_quality)

            # PyMuPDF quirk: update_stream(compress=False) strips /Filter from
            # the object dictionary, even if we set it via update_object first.
            # Workaround: omit /Filter from the dict, call update_stream, then
            # add /Filter /DCTDecode afterwards via xref_set_key.
            new_obj_def = (
                f"<<\n"
                f"  /Type /XObject /Subtype /Image\n"
                f"  /Width {pix.width} /Height {pix.height}\n"
                f"  /ColorSpace /DeviceRGB /BitsPerComponent 8\n"
                f"{smask_entry}"
                f">>"
            )
            doc.update_object(xref, new_obj_def)
            # compress=False: don't zlib-compress the stream — it's already JPEG
            doc.update_stream(xref, jpeg_bytes, compress=False)
            # Add /Filter AFTER update_stream, or it gets stripped
            doc.xref_set_key(xref, "Filter", "/DCTDecode")

        total_converted += 1
        print(f"    ✓ Done")

    # Optionally prompt for metadata and apply it to the document
    if metadata is not None:
        # Merge caller-supplied fields with existing doc metadata so that
        # fields like creator/producer (not shown in the GUI) are preserved.
        merged = dict(doc.metadata)
        merged.update({k: v for k, v in metadata.items() if v})
        doc.set_metadata(merged)
    elif prompt_for_metadata:
        print()
        metadata = prompt_metadata(doc.metadata)
        doc.set_metadata(metadata)

    # Save the modified PDF.
    # garbage=0: no garbage collection.
    # Some PDFs (particularly from print workflows) use hybrid or cross-reference
    # stream xref structures that MuPDF can render but cannot fully trace during
    # garbage collection. MuPDF's GC then removes "unfindable" objects — including
    # live images — causing blank spaces in the output. Since we replace image
    # streams in-place via update_object/update_stream, we never create orphaned
    # objects, so GC is not needed for correctness.
    # deflate_fonts=True: compress font streams for smaller file size.
    # deflate_images is intentionally left off — if enabled, PyMuPDF would
    # recompress our JPEG streams as FlateDecode, undoing our encoding work.
    doc.save(output_path, garbage=0, deflate_fonts=True)
    doc.close()

    if repaired_path:
        try:
            os.unlink(repaired_path)
        except OSError:
            pass

    print(f"\nDone! Converted {total_converted} image(s), skipped {total_skipped}.")
    print(f"Output saved to: {output_path}")


def main():
    """Parse command-line arguments and kick off processing."""
    if len(sys.argv) < 2:
        print("Usage: python pdf_images_to_rgb.py input.pdf [output.pdf] [--quality N] [--no-metadata]")
        sys.exit(1)

    input_path = sys.argv[1]
    if not Path(input_path).exists():
        print(f"Error: File not found — {input_path}")
        sys.exit(1)

    # Parse optional output path, --quality, and --no-metadata flags
    output_path = None
    jpeg_quality = DEFAULT_QUALITY
    prompt_for_metadata = True
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--quality" and i + 1 < len(args):
            jpeg_quality = int(args[i + 1])
            i += 2
        elif args[i] == "--no-metadata":
            prompt_for_metadata = False
            i += 1
        elif not args[i].startswith("--") and output_path is None:
            output_path = args[i]
            i += 1
        else:
            i += 1

    # Default output filename: append _rgb before the extension
    if output_path is None:
        p = Path(input_path)
        output_path = str(p.with_stem(p.stem + "_rgb"))

    print(f"Processing: {input_path}")
    print(f"Output:     {output_path}\n")

    process_pdf(input_path, output_path, jpeg_quality, prompt_for_metadata)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Native macOS GUI for mac-pdf-rgb-fix using PyObjC / AppKit.
Requires: pip3 install pyobjc-core pyobjc-framework-Cocoa --break-system-packages
Run:     python3 mac_pdf_rgb_fix_appkit.py
"""

import sys
import io
import threading
from pathlib import Path

import objc
from Foundation import NSObject, NSOperationQueue, NSAttributedString, NSNotFound
from AppKit import (
    NSApplication, NSApp,
    NSWindow, NSView, NSBox,
    NSButton, NSTextField,
    NSSlider, NSScrollView, NSTextView,
    NSTableView, NSTableColumn,
    NSOpenPanel,
    NSAlert,
    NSColor, NSFont,
    NSBackingStoreBuffered,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
    NSBezelStyleRounded,
    NSViewWidthSizable,
    NSApplicationActivationPolicyRegular,
)

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
PAD          = 20
SECTION_GAP  = 16
ROW_GAP      = 8
LABEL_W      = 90
BTN_W        = 90


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def on_main(fn):
    NSOperationQueue.mainQueue().addOperationWithBlock_(fn)


def make_label(text, font=None, color=None):
    lbl = NSTextField.alloc().initWithFrame_(((0, 0), (0, 0)))
    lbl.setStringValue_(text)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setBordered_(False)
    lbl.setDrawsBackground_(False)
    lbl.setFont_(font or NSFont.systemFontOfSize_(13))
    if color:
        lbl.setTextColor_(color)
    lbl.setTranslatesAutoresizingMaskIntoConstraints_(False)
    return lbl


def make_field(placeholder=""):
    f = NSTextField.alloc().initWithFrame_(((0, 0), (0, 0)))
    f.setPlaceholderString_(placeholder)
    f.setFont_(NSFont.systemFontOfSize_(13))
    f.setTranslatesAutoresizingMaskIntoConstraints_(False)
    return f


def pin(view, view_anchor, to, to_anchor, constant=0.0):
    getattr(view, view_anchor)().constraintEqualToAnchor_constant_(
        getattr(to, to_anchor)(), constant
    ).setActive_(True)


def pin_eq(view, view_anchor, to, to_anchor):
    getattr(view, view_anchor)().constraintEqualToAnchor_(
        getattr(to, to_anchor)()
    ).setActive_(True)


def pin_const(view, anchor, constant):
    getattr(view, anchor)().constraintEqualToConstant_(constant).setActive_(True)


def pin_ge(view, anchor, constant):
    getattr(view, anchor)().constraintGreaterThanOrEqualToConstant_(constant).setActive_(True)


# ---------------------------------------------------------------------------
# App delegate  (also acts as NSTableViewDataSource / NSTableViewDelegate)
# ---------------------------------------------------------------------------

class AppDelegate(NSObject):

    def applicationDidFinishLaunching_(self, _notif):
        self._input_files = []
        self._build_window()
        NSApp.activateIgnoringOtherApps_(True)

    def applicationShouldTerminateAfterLastWindowClosed_(self, _app):
        return True

    # ------------------------------------------------------------------
    # NSTableViewDataSource
    # ------------------------------------------------------------------

    def numberOfRowsInTableView_(self, table_view):
        return len(self._input_files)

    def tableView_objectValueForTableColumn_row_(self, table_view, column, row):
        if row < len(self._input_files):
            return Path(self._input_files[row]).name
        return ""

    # ------------------------------------------------------------------
    # Window / layout
    # ------------------------------------------------------------------

    @objc.python_method
    def _build_window(self):
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((200, 200), (700, 820)),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("mac-pdf-rgb-fix")
        self._window.setMinSize_((580, 700))
        self._window.center()
        self._setup_layout(self._window.contentView())
        self._window.makeKeyAndOrderFront_(None)

    @objc.python_method
    def _setup_layout(self, cv):
        # ── Title ──────────────────────────────────────────────────────────
        title = make_label(
            "mac-pdf-rgb-fix",
            font=NSFont.boldSystemFontOfSize_(22),
            color=NSColor.controlAccentColor(),
        )
        subtitle = make_label(
            "Apple-compatible PDF image converter",
            font=NSFont.systemFontOfSize_(12),
            color=NSColor.secondaryLabelColor(),
        )
        cv.addSubview_(title)
        cv.addSubview_(subtitle)

        pin(title,    "topAnchor",      cv,    "topAnchor",      PAD)
        pin(title,    "leadingAnchor",  cv,    "leadingAnchor",  PAD)
        pin(subtitle, "trailingAnchor", cv,    "trailingAnchor", -PAD)
        subtitle.firstBaselineAnchor().constraintEqualToAnchor_(
            title.firstBaselineAnchor()
        ).setActive_(True)

        prev = title

        # ── FILES ──────────────────────────────────────────────────────────
        prev = self._section_header(cv, "FILES", prev)

        # File list table
        self._file_table_scroll, self._file_table = self._make_file_table()
        cv.addSubview_(self._file_table_scroll)

        pin(self._file_table_scroll, "topAnchor",      prev, "bottomAnchor",   ROW_GAP)
        pin(self._file_table_scroll, "leadingAnchor",  cv,   "leadingAnchor",  PAD)
        pin(self._file_table_scroll, "trailingAnchor", cv,   "trailingAnchor", -PAD)
        pin_const(self._file_table_scroll, "heightAnchor", 110)

        # Add / Remove buttons
        add_btn    = self._make_button("Add Files…",       b"addFiles:")
        remove_btn = self._make_button("Remove Selected",  b"removeSelected:")
        cv.addSubview_(add_btn)
        cv.addSubview_(remove_btn)

        pin(add_btn,    "topAnchor",     self._file_table_scroll, "bottomAnchor",  6)
        pin(add_btn,    "leadingAnchor", cv,                      "leadingAnchor", PAD)
        pin(remove_btn, "topAnchor",     self._file_table_scroll, "bottomAnchor",  6)
        pin(remove_btn, "leadingAnchor", add_btn,                 "trailingAnchor", 8)

        prev = add_btn

        # ── JPEG QUALITY ───────────────────────────────────────────────────
        prev = self._section_header(cv, "JPEG QUALITY", prev)

        self._quality_label = make_label(
            "95",
            font=NSFont.monospacedDigitSystemFontOfSize_weight_(16, 0.0),
            color=NSColor.controlAccentColor(),
        )
        self._quality_slider = NSSlider.alloc().initWithFrame_(((0, 0), (0, 0)))
        self._quality_slider.setMinValue_(1)
        self._quality_slider.setMaxValue_(95)
        self._quality_slider.setIntValue_(95)
        self._quality_slider.setContinuous_(True)
        self._quality_slider.setTarget_(self)
        self._quality_slider.setAction_(b"qualityChanged:")
        self._quality_slider.setTranslatesAutoresizingMaskIntoConstraints_(False)

        tick_lo = make_label("1",  font=NSFont.systemFontOfSize_(10),
                             color=NSColor.secondaryLabelColor())
        tick_hi = make_label("95", font=NSFont.systemFontOfSize_(10),
                             color=NSColor.secondaryLabelColor())

        for v in (self._quality_label, self._quality_slider, tick_lo, tick_hi):
            cv.addSubview_(v)

        pin(self._quality_slider, "topAnchor",      prev,                 "bottomAnchor",  ROW_GAP)
        pin(self._quality_slider, "trailingAnchor", cv,                   "trailingAnchor", -PAD)
        pin(self._quality_slider, "leadingAnchor",  self._quality_label,  "trailingAnchor", 8)
        pin_eq(self._quality_label, "centerYAnchor", self._quality_slider, "centerYAnchor")
        pin(self._quality_label,  "leadingAnchor",  cv,                   "leadingAnchor", PAD)
        pin_const(self._quality_label, "widthAnchor", 38)

        pin(tick_lo, "topAnchor",      self._quality_slider, "bottomAnchor", 2)
        pin_eq(tick_lo, "leadingAnchor",  self._quality_slider, "leadingAnchor")
        pin(tick_hi, "topAnchor",      self._quality_slider, "bottomAnchor", 2)
        pin_eq(tick_hi, "trailingAnchor", self._quality_slider, "trailingAnchor")

        prev = tick_lo

        # ── PDF METADATA ───────────────────────────────────────────────────
        prev = self._section_header(cv, "PDF METADATA", prev)

        note = make_label("Leave blank to keep the existing values for each file",
                          font=NSFont.systemFontOfSize_(11),
                          color=NSColor.secondaryLabelColor())
        cv.addSubview_(note)
        pin(note, "topAnchor",     prev, "bottomAnchor", 2)
        pin(note, "leadingAnchor", cv,   "leadingAnchor", PAD)
        prev = note

        for label_text, attr in [("Title",    "_meta_title"),
                                  ("Author",   "_meta_author"),
                                  ("Subject",  "_meta_subject"),
                                  ("Keywords", "_meta_keywords")]:
            lbl   = make_label(label_text, color=NSColor.secondaryLabelColor())
            field = make_field(label_text)
            setattr(self, attr, field)
            cv.addSubview_(lbl)
            cv.addSubview_(field)

            pin(lbl,   "topAnchor",     prev,  "bottomAnchor", 14)
            pin(lbl,   "leadingAnchor", cv,    "leadingAnchor", PAD)
            pin_const(lbl, "widthAnchor", LABEL_W)
            pin_eq(field, "centerYAnchor", lbl,  "centerYAnchor")
            pin(field, "leadingAnchor",  lbl,  "trailingAnchor", 8)
            pin(field, "trailingAnchor", cv,   "trailingAnchor", -PAD)
            prev = lbl

        # ── Convert button ─────────────────────────────────────────────────
        self._convert_btn = NSButton.buttonWithTitle_target_action_(
            "Convert PDF", self, b"startConversion:"
        )
        self._convert_btn.setBezelStyle_(NSBezelStyleRounded)
        self._convert_btn.setFont_(NSFont.boldSystemFontOfSize_(14))
        self._convert_btn.setKeyEquivalent_("\r")
        self._convert_btn.setTranslatesAutoresizingMaskIntoConstraints_(False)
        cv.addSubview_(self._convert_btn)

        pin(self._convert_btn, "topAnchor",      prev, "bottomAnchor", SECTION_GAP)
        pin(self._convert_btn, "leadingAnchor",  cv,   "leadingAnchor",  PAD)
        pin(self._convert_btn, "trailingAnchor", cv,   "trailingAnchor", -PAD)

        # ── LOG ────────────────────────────────────────────────────────────
        log_hdr = self._section_header(cv, "LOG", self._convert_btn)
        self._log_scroll, self._log_text = self._make_text_view()
        cv.addSubview_(self._log_scroll)

        pin(self._log_scroll, "topAnchor",      log_hdr, "bottomAnchor",  ROW_GAP)
        pin(self._log_scroll, "leadingAnchor",  cv,      "leadingAnchor", PAD)
        pin(self._log_scroll, "trailingAnchor", cv,      "trailingAnchor", -PAD)
        pin(self._log_scroll, "bottomAnchor",   cv,      "bottomAnchor",  -PAD)
        pin_ge(self._log_scroll, "heightAnchor", 120)

    @objc.python_method
    def _section_header(self, cv, title, prev_view):
        lbl = make_label(title,
                         font=NSFont.boldSystemFontOfSize_(10),
                         color=NSColor.controlAccentColor())
        sep = NSBox.alloc().initWithFrame_(((0, 0), (0, 1)))
        sep.setBoxType_(2)
        sep.setTranslatesAutoresizingMaskIntoConstraints_(False)
        cv.addSubview_(lbl)
        cv.addSubview_(sep)

        pin(lbl, "topAnchor",      prev_view, "bottomAnchor",  SECTION_GAP)
        pin(lbl, "leadingAnchor",  cv,        "leadingAnchor", PAD)
        pin(sep, "leadingAnchor",  lbl,       "trailingAnchor", 8)
        pin(sep, "trailingAnchor", cv,        "trailingAnchor", -PAD)
        pin_eq(sep, "centerYAnchor", lbl, "centerYAnchor")
        return lbl

    @objc.python_method
    def _make_button(self, title, action):
        b = NSButton.buttonWithTitle_target_action_(title, self, action)
        b.setBezelStyle_(NSBezelStyleRounded)
        b.setTranslatesAutoresizingMaskIntoConstraints_(False)
        return b

    @objc.python_method
    def _make_file_table(self):
        col = NSTableColumn.alloc().initWithIdentifier_("file")
        col.setTitle_("Files")
        col.setEditable_(False)

        tv = NSTableView.alloc().initWithFrame_(((0, 0), (100, 100)))
        tv.addTableColumn_(col)
        tv.setDataSource_(self)
        tv.setDelegate_(self)
        tv.setAllowsMultipleSelection_(True)
        tv.setHeaderView_(None)
        tv.setColumnAutoresizingStyle_(1)   # NSTableViewUniformColumnAutoresizingStyle

        scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (100, 100)))
        scroll.setTranslatesAutoresizingMaskIntoConstraints_(False)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(1)
        scroll.setDocumentView_(tv)
        return scroll, tv

    @objc.python_method
    def _make_text_view(self):
        scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (100, 100)))
        scroll.setTranslatesAutoresizingMaskIntoConstraints_(False)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(1)

        tv = NSTextView.alloc().initWithFrame_(((0, 0), (100, 100)))
        tv.setMinSize_((0, 0))
        tv.setMaxSize_((1e7, 1e7))
        tv.setVerticallyResizable_(True)
        tv.setHorizontallyResizable_(False)
        tv.setAutoresizingMask_(NSViewWidthSizable)
        tv.setEditable_(False)
        tv.setSelectable_(True)
        tv.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, 0.0))
        tv.setAutomaticQuoteSubstitutionEnabled_(False)
        tv.setAutomaticDashSubstitutionEnabled_(False)
        if tv.textContainer():
            tv.textContainer().setContainerSize_((1e7, 1e7))
            tv.textContainer().setWidthTracksTextView_(True)

        scroll.setDocumentView_(tv)
        return scroll, tv

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def addFiles_(self, _sender):
        panel = NSOpenPanel.openPanel()
        panel.setTitle_("Select PDFs")
        panel.setAllowedFileTypes_(["pdf"])
        panel.setAllowsMultipleSelection_(True)
        panel.setAllowsOtherFileTypes_(False)
        if panel.runModal() == 1:
            added = False
            for url in panel.URLs():
                path = url.path()
                if path not in self._input_files:
                    self._input_files.append(path)
                    added = True
            if added:
                self._file_table.reloadData()
                self._prefill_metadata(self._input_files[0])

    def removeSelected_(self, _sender):
        indexes = self._file_table.selectedRowIndexes()
        rows = set()
        idx = indexes.firstIndex()
        while idx != NSNotFound:
            rows.add(idx)
            idx = indexes.indexGreaterThanIndex_(idx)
        self._input_files = [f for i, f in enumerate(self._input_files) if i not in rows]
        self._file_table.reloadData()

    @objc.python_method
    def _prefill_metadata(self, path):
        try:
            import fitz
            doc = fitz.open(path)
            meta = doc.metadata
            doc.close()
            for field, key in [(self._meta_title,    "title"),
                               (self._meta_author,   "author"),
                               (self._meta_subject,  "subject"),
                               (self._meta_keywords, "keywords")]:
                field.setStringValue_(meta.get(key) or "")
        except Exception as e:
            self._log(f"Warning: could not read metadata — {e}\n")

    def qualityChanged_(self, sender):
        self._quality_label.setStringValue_(str(int(sender.intValue())))

    def startConversion_(self, _sender):
        if not self._input_files:
            self._alert("Error", "Please add at least one input PDF.")
            return

        quality  = int(self._quality_slider.intValue())
        metadata = {
            "title":    self._meta_title.stringValue().strip(),
            "author":   self._meta_author.stringValue().strip(),
            "subject":  self._meta_subject.stringValue().strip(),
            "keywords": self._meta_keywords.stringValue().strip(),
        }
        files = list(self._input_files)
        n = len(files)

        self._convert_btn.setEnabled_(False)
        self._convert_btn.setTitle_(f"Converting 0 of {n}…")
        self._log_clear()

        threading.Thread(
            target=self._run_conversion,
            args=(files, quality, metadata),
            daemon=True,
        ).start()

    @objc.python_method
    def _run_conversion(self, files, quality, metadata):
        old_stdout = sys.stdout
        sys.stdout = _LogWriter(lambda t: on_main(lambda txt=t: self._log(txt)))
        errors = []
        n = len(files)
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from pdf_images_to_rgb import process_pdf_with_metadata

            for i, input_path in enumerate(files):
                p = Path(input_path)
                output_path = str(p.with_stem(p.stem + "_rgb"))
                label = f"Converting {i + 1} of {n}…"
                on_main(lambda t=label: self._convert_btn.setTitle_(t))
                print(f"[{i + 1}/{n}] {p.name}")
                try:
                    process_pdf_with_metadata(input_path, output_path, quality, metadata)
                    print(f"  → {output_path}\n")
                except Exception as exc:
                    errors.append((p.name, str(exc)))
                    print(f"  ✗ Error: {exc}\n")

            sys.stdout = old_stdout
            on_main(lambda: self._on_complete(n, errors))
        except Exception as exc:
            sys.stdout = old_stdout
            msg = str(exc)
            on_main(lambda m=msg: self._on_error(m))

    @objc.python_method
    def _on_complete(self, total, errors):
        self._convert_btn.setEnabled_(True)
        self._convert_btn.setTitle_("Convert PDF")
        if errors:
            detail = "\n".join(f"• {name}: {msg}" for name, msg in errors)
            self._alert(
                "Completed with errors",
                f"{total - len(errors)} of {total} file(s) converted.\n\n{detail}",
                is_error=True,
            )
        else:
            word = "file" if total == 1 else "files"
            self._alert("Done", f"All {total} {word} converted successfully.")

    @objc.python_method
    def _on_error(self, msg):
        self._log(f"\n✗ Error: {msg}\n")
        self._convert_btn.setEnabled_(True)
        self._convert_btn.setTitle_("Convert PDF")
        self._alert("Conversion Failed", msg, is_error=True)

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    @objc.python_method
    def _log(self, text):
        attr = NSAttributedString.alloc().initWithString_(text)
        self._log_text.textStorage().appendAttributedString_(attr)
        end = self._log_text.string().length()
        self._log_text.scrollRangeToVisible_((end, 0))

    @objc.python_method
    def _log_clear(self):
        self._log_text.setString_("")

    @objc.python_method
    def _alert(self, title, message, is_error=False):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        if is_error:
            alert.setAlertStyle_(2)
        alert.addButtonWithTitle_("OK")
        alert.runModal()


# ---------------------------------------------------------------------------
# stdout → log bridge
# ---------------------------------------------------------------------------

class _LogWriter(io.TextIOBase):
    def __init__(self, callback):
        self._cb  = callback
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._cb(line + "\n")
        return len(s)

    def flush(self):
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()

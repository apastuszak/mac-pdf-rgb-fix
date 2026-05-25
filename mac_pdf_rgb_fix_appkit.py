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
from Foundation import NSObject, NSOperationQueue, NSAttributedString
from AppKit import (
    NSApplication, NSApp,
    NSWindow, NSView, NSBox,
    NSButton, NSTextField,
    NSSlider, NSScrollView, NSTextView,
    NSOpenPanel, NSSavePanel,
    NSAlert,
    NSMenu, NSMenuItem,
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
    """Schedule fn() on the main thread (safe to call from any thread)."""
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
    """Activate: view.view_anchor == to.to_anchor + constant."""
    a = getattr(view, view_anchor)()
    b = getattr(to,   to_anchor)()
    a.constraintEqualToAnchor_constant_(b, constant).setActive_(True)


def pin_eq(view, view_anchor, to, to_anchor):
    """Activate: view.view_anchor == to.to_anchor (no constant)."""
    getattr(view, view_anchor)().constraintEqualToAnchor_(
        getattr(to, to_anchor)()
    ).setActive_(True)


def pin_const(view, anchor, constant):
    """Activate a fixed-size constraint."""
    getattr(view, anchor)().constraintEqualToConstant_(constant).setActive_(True)


def pin_ge(view, anchor, constant):
    """Activate a ≥ constant constraint."""
    getattr(view, anchor)().constraintGreaterThanOrEqualToConstant_(constant).setActive_(True)


# ---------------------------------------------------------------------------
# App delegate
# ---------------------------------------------------------------------------

class AppDelegate(NSObject):

    def applicationDidFinishLaunching_(self, _notif):
        self._output_manually_set = False
        self._build_menu()
        self._build_window()
        NSApp.activateIgnoringOtherApps_(True)

    @objc.python_method
    def _build_menu(self):
        menubar = NSMenu.alloc().init()
        app_item = NSMenuItem.alloc().init()
        menubar.addItem_(app_item)
        NSApp.setMainMenu_(menubar)

        app_menu = NSMenu.alloc().init()
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit mac-pdf-rgb-fix", b"terminate:", "q"
        )
        app_menu.addItem_(quit_item)
        app_item.setSubmenu_(app_menu)

    def applicationShouldTerminateAfterLastWindowClosed_(self, _app):
        return True

    # ------------------------------------------------------------------
    # Window / layout
    # ------------------------------------------------------------------

    @objc.python_method
    def _build_window(self):
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((200, 200), (700, 780)),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("mac-pdf-rgb-fix")
        self._window.setMinSize_((580, 660))
        self._window.center()
        self._setup_layout(self._window.contentView())
        self._window.makeKeyAndOrderFront_(None)

    @objc.python_method
    def _setup_layout(self, cv):
        # ── Title row ──────────────────────────────────────────────────────
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

        pin(title, "topAnchor",      cv,    "topAnchor",      PAD)
        pin(title, "leadingAnchor",  cv,    "leadingAnchor",  PAD)
        pin(subtitle, "trailingAnchor", cv, "trailingAnchor", -PAD)
        subtitle.firstBaselineAnchor().constraintEqualToAnchor_(
            title.firstBaselineAnchor()
        ).setActive_(True)

        prev = title   # track last view for chaining

        # ── FILES ──────────────────────────────────────────────────────────
        prev = self._section_header(cv, "FILES", prev)

        self._input_field  = make_field("Select a PDF to convert…")
        self._output_field = make_field("Output path (auto-filled from input)")
        input_btn  = self._make_button("Choose…", b"chooseInput:")
        output_btn = self._make_button("Choose…", b"chooseOutput:")
        input_lbl  = make_label("Input PDF",  color=NSColor.secondaryLabelColor())
        output_lbl = make_label("Output PDF", color=NSColor.secondaryLabelColor())

        for v in (input_lbl, self._input_field, input_btn,
                  output_lbl, self._output_field, output_btn):
            cv.addSubview_(v)

        prev = self._file_row(cv, input_lbl,  self._input_field,  input_btn,  prev)
        prev = self._file_row(cv, output_lbl, self._output_field, output_btn, prev, gap=16)

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

        # Slider row: [value_label] [=====slider=====]
        pin(self._quality_slider, "topAnchor",     prev,                  "bottomAnchor", ROW_GAP)
        pin(self._quality_slider, "trailingAnchor", cv,                   "trailingAnchor", -PAD)
        pin(self._quality_slider, "leadingAnchor",  self._quality_label,  "trailingAnchor", 8)
        pin_eq(self._quality_label, "centerYAnchor", self._quality_slider, "centerYAnchor")
        pin(self._quality_label, "leadingAnchor", cv, "leadingAnchor", PAD)
        pin_const(self._quality_label, "widthAnchor", 38)

        # Tick labels below slider
        pin(tick_lo, "topAnchor",     self._quality_slider, "bottomAnchor", 2)
        pin_eq(tick_lo, "leadingAnchor", self._quality_slider, "leadingAnchor")
        pin(tick_hi, "topAnchor",     self._quality_slider, "bottomAnchor", 2)
        pin_eq(tick_hi, "trailingAnchor", self._quality_slider, "trailingAnchor")

        prev = tick_lo

        # ── PDF METADATA ───────────────────────────────────────────────────
        prev = self._section_header(cv, "PDF METADATA", prev)

        note = make_label("Leave blank to keep the existing PDF values",
                          font=NSFont.systemFontOfSize_(11),
                          color=NSColor.secondaryLabelColor())
        cv.addSubview_(note)
        pin(note, "topAnchor",     prev, "bottomAnchor", 2)
        pin(note, "leadingAnchor", cv,   "leadingAnchor", PAD)
        prev = note

        meta_rows = [
            ("Title",    "_meta_title"),
            ("Author",   "_meta_author"),
            ("Subject",  "_meta_subject"),
            ("Keywords", "_meta_keywords"),
        ]
        for label_text, attr in meta_rows:
            lbl   = make_label(label_text, color=NSColor.secondaryLabelColor())
            field = make_field(label_text)
            setattr(self, attr, field)
            cv.addSubview_(lbl)
            cv.addSubview_(field)

            pin(lbl,   "topAnchor",     prev,  "bottomAnchor", 14)
            pin(lbl,   "leadingAnchor", cv,    "leadingAnchor", PAD)
            pin_const(lbl, "widthAnchor", LABEL_W)
            pin_eq(field, "centerYAnchor", lbl, "centerYAnchor")
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
        """Add bold-label + separator rule below prev_view; return the label."""
        lbl = make_label(title,
                         font=NSFont.boldSystemFontOfSize_(10),
                         color=NSColor.controlAccentColor())
        sep = NSBox.alloc().initWithFrame_(((0, 0), (0, 1)))
        sep.setBoxType_(2)   # NSBoxSeparator
        sep.setTranslatesAutoresizingMaskIntoConstraints_(False)
        cv.addSubview_(lbl)
        cv.addSubview_(sep)

        pin(lbl, "topAnchor",     prev_view, "bottomAnchor",  SECTION_GAP)
        pin(lbl, "leadingAnchor", cv,        "leadingAnchor", PAD)
        pin(sep, "leadingAnchor", lbl,       "trailingAnchor", 8)
        pin(sep, "trailingAnchor", cv,       "trailingAnchor", -PAD)
        pin_eq(sep, "centerYAnchor", lbl, "centerYAnchor")

        return lbl

    @objc.python_method
    def _file_row(self, cv, lbl, field, btn, prev_view, gap=ROW_GAP):
        """Lay out label + text field + button below prev_view; return label."""
        pin(lbl,   "topAnchor",      prev_view, "bottomAnchor",  gap)
        pin(lbl,   "leadingAnchor",  cv,        "leadingAnchor", PAD)
        pin_const(lbl, "widthAnchor", LABEL_W)
        pin_eq(field, "centerYAnchor", lbl, "centerYAnchor")
        pin(field, "leadingAnchor",  lbl, "trailingAnchor",  8)
        pin(field, "trailingAnchor", btn, "leadingAnchor",  -8)
        pin_eq(btn, "centerYAnchor", lbl, "centerYAnchor")
        pin(btn,   "trailingAnchor", cv,  "trailingAnchor", -PAD)
        pin_const(btn, "widthAnchor", BTN_W)
        return lbl

    @objc.python_method
    def _make_button(self, title, action):
        b = NSButton.buttonWithTitle_target_action_(title, self, action)
        b.setBezelStyle_(NSBezelStyleRounded)
        b.setTranslatesAutoresizingMaskIntoConstraints_(False)
        return b

    @objc.python_method
    def _make_text_view(self):
        scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (100, 100)))
        scroll.setTranslatesAutoresizingMaskIntoConstraints_(False)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setBorderType_(1)   # NSBezelBorder

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

    def chooseInput_(self, _sender):
        panel = NSOpenPanel.openPanel()
        panel.setTitle_("Select Input PDF")
        panel.setAllowedFileTypes_(["pdf"])
        panel.setAllowsOtherFileTypes_(False)
        if panel.runModal() == 1:   # NSModalResponseOK
            path = panel.URL().path()
            self._input_field.setStringValue_(path)
            self._on_input_changed(path)

    def chooseOutput_(self, _sender):
        panel = NSSavePanel.savePanel()
        panel.setTitle_("Save Output PDF")
        panel.setAllowedFileTypes_(["pdf"])
        existing = self._output_field.stringValue()
        if existing:
            panel.setNameFieldStringValue_(Path(existing).name)
        if panel.runModal() == 1:
            self._output_manually_set = True
            self._output_field.setStringValue_(panel.URL().path())

    @objc.python_method
    def _on_input_changed(self, path):
        if not self._output_manually_set:
            p = Path(path)
            self._output_field.setStringValue_(str(p.with_stem(p.stem + "_rgb")))

        if Path(path).exists():
            try:
                import fitz
                doc = fitz.open(path)
                meta = doc.metadata
                doc.close()
                for field, key in [
                    (self._meta_title,    "title"),
                    (self._meta_author,   "author"),
                    (self._meta_subject,  "subject"),
                    (self._meta_keywords, "keywords"),
                ]:
                    field.setStringValue_(meta.get(key) or "")
            except Exception as e:
                self._log(f"Warning: could not read metadata — {e}\n")

    def qualityChanged_(self, sender):
        self._quality_label.setStringValue_(str(int(sender.intValue())))

    def startConversion_(self, _sender):
        input_path  = self._input_field.stringValue().strip()
        output_path = self._output_field.stringValue().strip()

        if not input_path:
            self._alert("Error", "Please select an input PDF.")
            return
        if not Path(input_path).exists():
            self._alert("Error", f"Input file not found:\n{input_path}")
            return
        if not output_path:
            self._alert("Error", "Please specify an output path.")
            return

        quality  = int(self._quality_slider.intValue())
        metadata = {
            "title":    self._meta_title.stringValue().strip(),
            "author":   self._meta_author.stringValue().strip(),
            "subject":  self._meta_subject.stringValue().strip(),
            "keywords": self._meta_keywords.stringValue().strip(),
        }

        self._convert_btn.setEnabled_(False)
        self._convert_btn.setTitle_("Converting…")
        self._log_clear()
        self._log(f"Input:   {input_path}\n")
        self._log(f"Output:  {output_path}\n")
        self._log(f"Quality: {quality}\n\n")

        threading.Thread(
            target=self._run_conversion,
            args=(input_path, output_path, quality, metadata),
            daemon=True,
        ).start()

    @objc.python_method
    def _run_conversion(self, input_path, output_path, quality, metadata):
        old_stdout = sys.stdout
        sys.stdout = _LogWriter(lambda t: on_main(lambda txt=t: self._log(txt)))
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from pdf_images_to_rgb import process_pdf_with_metadata
            process_pdf_with_metadata(input_path, output_path, quality, metadata)
            sys.stdout = old_stdout
            on_main(lambda: self._on_success(output_path))
        except Exception as exc:
            sys.stdout = old_stdout
            msg = str(exc)
            on_main(lambda m=msg: self._on_error(m))

    @objc.python_method
    def _on_success(self, output_path):
        self._log(f"\n✓ Saved to {output_path}\n")
        self._convert_btn.setEnabled_(True)
        self._convert_btn.setTitle_("Convert PDF")
        self._alert("Done", f"Conversion complete!\n\n{output_path}")

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

    # ------------------------------------------------------------------
    # Alert helper
    # ------------------------------------------------------------------

    @objc.python_method
    def _alert(self, title, message, is_error=False):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        if is_error:
            alert.setAlertStyle_(2)   # NSAlertStyleCritical
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

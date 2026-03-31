from __future__ import print_function

import traceback

from java.awt import BorderLayout
from java.awt import FlowLayout
from java.awt.event import ActionListener
from java.lang import Runnable, Thread

from javax.swing import BorderFactory
from javax.swing import JButton
from javax.swing import JCheckBox
from javax.swing import JFrame
from javax.swing import JLabel
from javax.swing import JOptionPane
from javax.swing import JPanel
from javax.swing import JScrollPane
from javax.swing import JSplitPane
from javax.swing import JTextArea
from javax.swing import SwingUtilities

from ghidra_ai_chat.config import DEFAULT_SETTINGS
from ghidra_ai_chat.context.collect import collect_context
from ghidra_ai_chat.llm.client import build_client, LLMError
from ghidra_ai_chat.prompts.templates import build_messages, format_context_block
from ghidra_ai_chat.store.conversation import load_history, save_history


class _UiRunnable(Runnable):
    def __init__(self, fn):
        self._fn = fn

    def run(self):
        self._fn()


def _invoke_later(fn):
    SwingUtilities.invokeLater(_UiRunnable(fn))


def _append_transcript(area, who, text):
    existing = area.getText()
    chunk = "[%s]\n%s\n\n" % (who, text)
    area.setText(existing + chunk)
    area.setCaretPosition(len(area.getText()))


class ChatWindow(object):
    def __init__(self, script):
        self.script = script
        self.settings = DEFAULT_SETTINGS
        self.client = build_client(self.settings)

        # runtime state
        self.captured_context = None
        self.history = []

        self._build_ui()
        self._refresh_context(capture=True)
        self._load_history_from_disk()

    def _build_ui(self):
        self.frame = JFrame("Ghidra AI Chat Agent")
        self.frame.setSize(980, 720)
        self.frame.setLayout(BorderLayout())

        self.transcript = JTextArea()
        self.transcript.setEditable(False)
        self.transcript.setLineWrap(True)
        self.transcript.setWrapStyleWord(True)

        self.context_preview = JTextArea()
        self.context_preview.setEditable(False)
        self.context_preview.setLineWrap(True)
        self.context_preview.setWrapStyleWord(True)

        left = JScrollPane(self.transcript)
        right = JScrollPane(self.context_preview)
        split = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, left, right)
        split.setDividerLocation(560)
        split.setResizeWeight(0.7)

        self.frame.add(split, BorderLayout.CENTER)

        # Top controls
        top = JPanel(FlowLayout(FlowLayout.LEFT))
        top.setBorder(BorderFactory.createEmptyBorder(4, 6, 4, 6))

        self.cb_decompile = JCheckBox("decompile", True)
        self.cb_strings = JCheckBox("strings", False)
        self.cb_imports = JCheckBox("imports", False)
        self.cb_xrefs = JCheckBox("xrefs", False)

        top.add(JLabel("Context:"))
        top.add(self.cb_decompile)
        top.add(self.cb_strings)
        top.add(self.cb_imports)
        top.add(self.cb_xrefs)

        self.btn_capture = JButton("Capture")
        self.btn_preview = JButton("Preview")
        self.btn_settings = JButton("Settings")
        self.btn_clear = JButton("Clear")

        top.add(self.btn_capture)
        top.add(self.btn_preview)
        top.add(self.btn_settings)
        top.add(self.btn_clear)

        self.frame.add(top, BorderLayout.NORTH)

        # Bottom input
        bottom = JPanel()
        bottom.setLayout(BorderLayout())
        bottom.setBorder(BorderFactory.createEmptyBorder(6, 6, 6, 6))

        self.input = JTextArea(4, 80)
        self.input.setLineWrap(True)
        self.input.setWrapStyleWord(True)
        bottom.add(JScrollPane(self.input), BorderLayout.CENTER)

        send_row = JPanel(FlowLayout(FlowLayout.RIGHT))
        self.btn_send = JButton("Send")
        send_row.add(self.btn_send)
        bottom.add(send_row, BorderLayout.SOUTH)

        self.frame.add(bottom, BorderLayout.SOUTH)

        # Actions
        self.btn_send.addActionListener(_Action(lambda e: self._on_send()))
        self.btn_capture.addActionListener(_Action(lambda e: self._on_capture()))
        self.btn_preview.addActionListener(_Action(lambda e: self._on_preview()))
        self.btn_settings.addActionListener(_Action(lambda e: self._on_settings()))
        self.btn_clear.addActionListener(_Action(lambda e: self._on_clear()))

        # Toggle changes update settings + preview
        self.cb_decompile.addActionListener(_Action(lambda e: self._sync_toggles()))
        self.cb_strings.addActionListener(_Action(lambda e: self._sync_toggles()))
        self.cb_imports.addActionListener(_Action(lambda e: self._sync_toggles()))
        self.cb_xrefs.addActionListener(_Action(lambda e: self._sync_toggles()))

    def show(self):
        self.frame.setVisible(True)
        _append_transcript(self.transcript, "system", "Ready. Open a program and place cursor in a function, then ask a question.")
        _append_transcript(
            self.transcript,
            "system",
            "API key source: %s" % self.settings.api_key_source(),
        )
        self._update_context_preview()

    def _sync_toggles(self):
        self.settings.include_decompile = bool(self.cb_decompile.isSelected())
        self.settings.include_strings = bool(self.cb_strings.isSelected())
        self.settings.include_imports = bool(self.cb_imports.isSelected())
        self.settings.include_xrefs = bool(self.cb_xrefs.isSelected())
        self._refresh_context(capture=True)
        self._update_context_preview()

    def _refresh_context(self, capture):
        ctx = collect_context(self.script, self.settings)
        if capture:
            self.captured_context = ctx
        return ctx

    def _update_context_preview(self):
        ctx = self.captured_context or self._refresh_context(capture=True)
        txt = format_context_block(ctx, self.settings)
        self.context_preview.setText(txt)
        self.context_preview.setCaretPosition(0)

    def _load_history_from_disk(self):
        # history key depends on program, so use current captured context
        ctx = self.captured_context or self._refresh_context(capture=True)
        self.history = load_history(ctx)
        if self.history:
            _append_transcript(self.transcript, "system", "Loaded %d prior messages for this program." % len(self.history))

    def _save_history_to_disk(self):
        ctx = self.captured_context or self._refresh_context(capture=True)
        save_history(ctx, self.history)

    def _on_clear(self):
        self.transcript.setText("")
        self.history = []
        self._save_history_to_disk()
        _append_transcript(self.transcript, "system", "Cleared conversation.")

    def _on_capture(self):
        self._refresh_context(capture=True)
        self._update_context_preview()
        _append_transcript(self.transcript, "system", "Captured context from current cursor/function.")

    def _on_preview(self):
        self._refresh_context(capture=True)
        self._update_context_preview()
        # Use a fresh read-only text area so dialog scroll doesn't affect side panel state
        ta = JTextArea(self.context_preview.getText())
        ta.setEditable(False)
        ta.setLineWrap(True)
        ta.setWrapStyleWord(True)
        ta.setCaretPosition(0)
        JOptionPane.showMessageDialog(
            self.frame,
            JScrollPane(ta),
            "Context Preview (will be sent)",
            JOptionPane.INFORMATION_MESSAGE,
        )

    def _on_settings(self):
        model = JOptionPane.showInputDialog(self.frame, "Model name:", self.settings.model)
        if model:
            self.settings.model = model.strip()
        key_path = JOptionPane.showInputDialog(
            self.frame,
            "Session key file path (raw API key text; delete after use):",
            self.settings.api_key_file_path,
        )
        if key_path:
            self.settings.api_key_file_path = key_path.strip()
        try:
            mot = JOptionPane.showInputDialog(self.frame, "Max output tokens:", str(self.settings.max_output_tokens))
            if mot:
                self.settings.max_output_tokens = int(mot.strip())
        except Exception:
            pass
        try:
            mcc = JOptionPane.showInputDialog(self.frame, "Max context chars:", str(self.settings.max_context_chars))
            if mcc:
                self.settings.max_context_chars = int(mcc.strip())
        except Exception:
            pass
        _append_transcript(
            self.transcript,
            "system",
            "Updated settings. API key source now: %s" % self.settings.api_key_source(),
        )
        self._on_capture()

    def _on_send(self):
        q = self.input.getText().strip()
        if not q:
            return
        self.input.setText("")

        # Always capture latest context at send time (acts like VS Code's implicit context)
        ctx = self._refresh_context(capture=True)
        self._update_context_preview()
        ctx_str = format_context_block(ctx, self.settings)

        _append_transcript(self.transcript, "user", q)
        self.history.append({"role": "user", "content": q})
        self._save_history_to_disk()

        def worker():
            try:
                msgs = build_messages(q, ctx_str, self.history, self.settings)
                ans = self.client.chat(msgs, self.settings)
                if ans is None:
                    ans = ""

                def ui_ok():
                    _append_transcript(self.transcript, "assistant", ans.strip())
                    self.history.append({"role": "assistant", "content": ans.strip()})
                    self._save_history_to_disk()

                _invoke_later(ui_ok)
            except LLMError as e:
                def ui_err():
                    _append_transcript(self.transcript, "error", str(e))
                _invoke_later(ui_err)
            except Exception as e:
                tb = traceback.format_exc()
                def ui_err2():
                    _append_transcript(self.transcript, "error", "%s\n\n%s" % (str(e), tb))
                _invoke_later(ui_err2)

        Thread(worker, "ghidra-ai-chat-worker").start()


class _Action(ActionListener):
    def __init__(self, fn):
        self.fn = fn

    def actionPerformed(self, e):
        try:
            self.fn(e)
        except Exception:
            # Avoid killing UI thread; errors show in transcript on send anyway.
            pass


def launch_chat_window(script):
    w = ChatWindow(script)
    w.show()
    return w


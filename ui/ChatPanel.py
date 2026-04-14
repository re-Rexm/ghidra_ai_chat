from __future__ import print_function

import os
import re
import traceback

from java.awt import BorderLayout
from java.awt import FlowLayout
from java.awt.event import ActionListener
from java.lang import Runnable, Thread

from javax.swing import BorderFactory
from javax.swing import BoxLayout
from javax.swing import ButtonGroup
from javax.swing import JButton
from javax.swing import JCheckBox
from javax.swing import JFrame
from javax.swing import JLabel
from javax.swing import JOptionPane
from javax.swing import JPanel
from javax.swing import JRadioButton
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


def _one_line_cursor(ctx):
    if not ctx or ctx.get("error"):
        return "Cursor: (no context)"
    loc = ctx.get("location") or {}
    fn = (ctx.get("function") or {}).get("name") or ""
    addr = loc.get("address") or ""
    gh = loc.get("ghidraLocation") or ""
    if len(gh) > 120:
        gh = gh[:117] + "..."
    bits = []
    if fn:
        bits.append("fn=%s" % fn)
    if addr:
        bits.append(addr)
    if gh:
        bits.append(gh)
    if not bits:
        return "Cursor: (no address - click listing/decompiler)"
    return "Cursor: " + " | ".join(bits)


class ChatWindow(object):
    def __init__(self, script):
        self.script = script
        self.settings = DEFAULT_SETTINGS
        self.client = build_client(self.settings)
        self._ui_ready = False

        # runtime state
        self.captured_context = None
        self.history = []

        self._build_ui()
        self._sync_provider_ui()
        self._ui_ready = True
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

        # Top controls (stacked rows)
        top_wrap = JPanel()
        top_wrap.setLayout(BoxLayout(top_wrap, BoxLayout.Y_AXIS))
        top_wrap.setBorder(BorderFactory.createEmptyBorder(4, 6, 4, 6))

        row_llm = JPanel(FlowLayout(FlowLayout.LEFT))
        row_llm.add(JLabel("LLM:"))
        self.rb_openrouter = JRadioButton("OpenRouter")
        self.rb_gemini = JRadioButton("Gemini")
        self.bg_llm = ButtonGroup()
        self.bg_llm.add(self.rb_openrouter)
        self.bg_llm.add(self.rb_gemini)
        row_llm.add(self.rb_openrouter)
        row_llm.add(self.rb_gemini)
        top_wrap.add(row_llm)

        self.lbl_cursor = JLabel("Cursor: ...")
        row_cur = JPanel(FlowLayout(FlowLayout.LEFT))
        row_cur.add(self.lbl_cursor)
        top_wrap.add(row_cur)

        row_ctx = JPanel(FlowLayout(FlowLayout.LEFT))
        self.cb_decompile = JCheckBox("decompile", True)
        self.cb_strings = JCheckBox("strings", False)
        self.cb_imports = JCheckBox("imports", False)
        self.cb_xrefs = JCheckBox("xrefs", False)

        row_ctx.add(JLabel("Context:"))
        row_ctx.add(self.cb_decompile)
        row_ctx.add(self.cb_strings)
        row_ctx.add(self.cb_imports)
        row_ctx.add(self.cb_xrefs)

        self.btn_capture = JButton("Capture")
        self.btn_preview = JButton("Preview")
        self.btn_settings = JButton("Settings")
        self.btn_clear = JButton("Clear")
        self.btn_extract = JButton("Extract Code")
        self.btn_agent = JButton("Apply Agent Action")

        row_ctx.add(self.btn_capture)
        row_ctx.add(self.btn_preview)
        row_ctx.add(self.btn_settings)
        row_ctx.add(self.btn_clear)
        row_ctx.add(self.btn_extract)
        row_ctx.add(self.btn_agent)

        top_wrap.add(row_ctx)
        self.frame.add(top_wrap, BorderLayout.NORTH)

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
        self.btn_extract.addActionListener(_Action(lambda e: self._on_extract()))
        self.btn_agent.addActionListener(_Action(lambda e: self._on_agent()))

        # Toggle changes update settings + preview
        self.cb_decompile.addActionListener(_Action(lambda e: self._sync_toggles()))
        self.cb_strings.addActionListener(_Action(lambda e: self._sync_toggles()))
        self.cb_imports.addActionListener(_Action(lambda e: self._sync_toggles()))
        self.cb_xrefs.addActionListener(_Action(lambda e: self._sync_toggles()))

        self.rb_openrouter.addActionListener(_Action(lambda e: self._on_llm_changed()))
        self.rb_gemini.addActionListener(_Action(lambda e: self._on_llm_changed()))

    def _sync_provider_ui(self):
        p = (self.settings.provider or "openrouter").strip().lower()
        if p == "gemini":
            self.rb_gemini.setSelected(True)
        else:
            self.rb_openrouter.setSelected(True)

    def _on_llm_changed(self):
        if not getattr(self, "_ui_ready", False):
            return
        if self.rb_gemini.isSelected():
            self.settings.provider = "gemini"
        else:
            self.settings.provider = "openrouter"
        self.client = build_client(self.settings)
        _append_transcript(
            self.transcript,
            "system",
            "Switched LLM to %s | keys: %s"
            % (self.settings.provider, self.settings.api_key_source()),
        )
        self._refresh_context(capture=True)
        self._update_context_preview()

    def show(self):
        self.frame.setVisible(True)
        _append_transcript(self.transcript, "system", "Ready. Open a program and place cursor in a function, then ask a question.")
        _append_transcript(
            self.transcript,
            "system",
            "API key source: %s" % self.settings.api_key_source(),
        )
        _append_transcript(
            self.transcript,
            "system",
            "Keys: use ~/Downloads/api_keys.txt with lines openrouter=KEY and gemini=KEY, "
            "or separate files (openrouter_api_key.txt / gemini_api_key.txt).",
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
        try:
            self.lbl_cursor.setText(_one_line_cursor(ctx))
        except Exception:
            pass
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

    def _on_extract(self):
        last_msg = self.history[-1] if self.history and self.history[-1]['role'] == 'assistant' else None
        if not last_msg:
            JOptionPane.showMessageDialog(self.frame, "No assistant message found.")
            return
        content = last_msg['content']
        code_blocks = re.findall(r'```python\n(.*?)\n```', content, re.DOTALL)
        if not code_blocks:
            JOptionPane.showMessageDialog(self.frame, "No Python code blocks found in last response.")
            return
        code = code_blocks[0]
        ta = JTextArea(code)
        ta.setEditable(True)
        ta.setLineWrap(True)
        ta.setWrapStyleWord(True)
        ta.setCaretPosition(0)
        JOptionPane.showMessageDialog(
            self.frame,
            JScrollPane(ta),
            "Extracted Code - Copy to new Ghidra script",
            JOptionPane.INFORMATION_MESSAGE,
        )

    def _on_agent(self):
        last_msg = self.history[-1] if self.history and self.history[-1]['role'] == 'assistant' else None
        if not last_msg:
            JOptionPane.showMessageDialog(self.frame, "No assistant message found.")
            return
        content = last_msg['content']
        # Parse for Action: ...
        action_match = re.search(r'Action:\s*(\w+)', content, re.IGNORECASE)
        if not action_match:
            JOptionPane.showMessageDialog(self.frame, "No 'Action: XXX' found in last response.")
            return
        action = action_match.group(1).lower()
        params = {}
        # Parse parameters like Name: value
        param_matches = re.findall(r'(\w+):\s*(.+)', content)
        for key, value in param_matches:
            params[key.lower()] = value.strip()
        
        # Define actions
        if action == 'rename_function':
            self._agent_rename_function(params)
        elif action == 'add_comment':
            self._agent_add_comment(params)
        else:
            JOptionPane.showMessageDialog(self.frame, "Unknown action: %s" % action)

    def _agent_rename_function(self, params):
        name = params.get('name')
        if not name:
            JOptionPane.showMessageDialog(self.frame, "No 'Name' parameter found.")
            return
        func = self.script.currentFunction
        if func is None:
            JOptionPane.showMessageDialog(self.frame, "No function at current cursor.")
            return
        try:
            func.setName(name)
            _append_transcript(self.transcript, "system", "Renamed function to '%s'." % name)
            self._refresh_context(capture=True)
            self._update_context_preview()
        except Exception as e:
            _append_transcript(self.transcript, "error", "Failed to rename: %s" % str(e))

    def _agent_add_comment(self, params):
        comment = params.get('comment')
        if not comment:
            JOptionPane.showMessageDialog(self.frame, "No 'Comment' parameter found.")
            return
        func = self.script.currentFunction
        if func is None:
            JOptionPane.showMessageDialog(self.frame, "No function at current cursor.")
            return
        try:
            func.setComment(comment)
            _append_transcript(self.transcript, "system", "Added comment to function.")
            self._refresh_context(capture=True)
            self._update_context_preview()
        except Exception as e:
            _append_transcript(self.transcript, "error", "Failed to add comment: %s" % str(e))

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
        keys_path = JOptionPane.showInputDialog(
            self.frame,
            "Optional: path to api_keys.txt (openrouter= / gemini= lines). Leave empty to use defaults:",
            os.environ.get(self.settings.keys_file_env_var, "") or "",
        )
        if keys_path:
            os.environ[self.settings.keys_file_env_var] = keys_path.strip()
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

        # Use cached context if decompile succeeded, else refresh
        if self.captured_context and self.captured_context.get('decompile') and not self.captured_context['decompile'].startswith('/*'):
            ctx = self.captured_context
        else:
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


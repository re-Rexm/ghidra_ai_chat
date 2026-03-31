
#@author 
#@category _NEW_
#@keybinding 
#@menupath 
#@toolbar 
#@runtime Jython

from __future__ import print_function

import sys

# Jython sometimes needs sys.path help when scripts are nested
import os
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)

from ghidra_ai_chat.ui.ChatPanel import launch_chat_window


class _ScriptCtx(object):
    """
    Bridge Ghidra Python globals into attribute-style access expected by modules.
    """

    def __init__(self, g):
        self.currentProgram = g.get("currentProgram", None)
        self.currentAddress = g.get("currentAddress", None)
        self.currentFunction = g.get("currentFunction", None)
        self.monitor = g.get("monitor", None)


def _main():
    script_ctx = _ScriptCtx(globals())
    if script_ctx.currentProgram is None:
        raise RuntimeError("No program is open. Load a binary in Ghidra first.")
    launch_chat_window(script_ctx)


_main()


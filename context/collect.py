from __future__ import print_function

import re

from ghidra.app.decompiler import DecompInterface


def _safe_str(x):
    try:
        return str(x)
    except Exception:
        try:
            return repr(x)
        except Exception:
            return "<unprintable>"


def _addr_to_str(addr):
    if addr is None:
        return ""
    try:
        return addr.toString()
    except Exception:
        return str(addr)


def _location_to_str(loc):
    if loc is None:
        return ""
    try:
        return _safe_str(loc.toString())
    except Exception:
        return _safe_str(loc)


def _get_function_at(script, addr):
    if addr is None:
        return None
    p = script.currentProgram
    if p is None:
        return None
    try:
        return p.getFunctionManager().getFunctionContaining(addr)
    except Exception:
        return None


def _collect_disassembly_window(program, addr, before, after):
    if program is None or addr is None:
        return ""
    listing = program.getListing()
    ins = None
    try:
        ins = listing.getInstructionContaining(addr)
    except Exception:
        ins = None
    if ins is None:
        try:
            ins = listing.getInstructionAt(addr)
        except Exception:
            ins = None
    if ins is None:
        try:
            cu = listing.getCodeUnitContaining(addr)
            if cu is not None:
                return "%s: %s" % (_addr_to_str(addr), cu.toString())
        except Exception:
            pass
        return ""

    try:
        cursor_addr = ins.getAddress()
        addr_ptr = cursor_addr
        for _ in range(max(0, int(before))):
            try:
                prev_a = listing.getInstructionBefore(addr_ptr)
                if prev_a is None:
                    break
                addr_ptr = prev_a
            except Exception:
                break

        lines = []
        total = max(1, int(before) + int(after) + 1)
        walk = addr_ptr
        for _ in range(total):
            cur_ins = listing.getInstructionAt(walk)
            if cur_ins is None:
                break
            try:
                la = cur_ins.getAddress()
                mark = " <-- cursor" if la.equals(cursor_addr) else ""
                lines.append("%s: %s%s" % (_addr_to_str(la), cur_ins.toString(), mark))
            except Exception:
                pass
            try:
                nxt = listing.getInstructionAfter(walk)
                if nxt is None:
                    break
                walk = nxt
            except Exception:
                break
        return "\n".join(lines)
    except Exception:
        return ""


def _get_fresh_monitor():
    try:
        from ghidra.util.task import ConsoleTaskMonitor
        return ConsoleTaskMonitor()
    except Exception:
        return None

def _decompile_function(script, func, timeout_seconds):
    if func is None:
        return "/* no function at cursor */"

    p = script.currentProgram
    if p is None:
        return "/* no program */"

    monitor = _get_fresh_monitor()
    print("[decompile] func=%s timeout=%s monitor=%s" % (
        func.getName(), timeout_seconds, monitor))

    di = DecompInterface()
    try:
        ok = di.openProgram(p)
        print("[decompile] openProgram returned: %s" % ok)
        if not ok:
            return "/* DecompInterface.openProgram returned False */"

        res = None
        try:
            res = di.decompileFunction(func, int(timeout_seconds), monitor)
        except Exception as e:
            return "/* decompileFunction raised: %s */" % _safe_str(e)

        print("[decompile] res=%s" % res)
        if res is None:
            return "/* decompileFunction returned None */"

        completed = False
        try:
            completed = res.decompileCompleted()
        except Exception as e:
            return "/* decompileCompleted() raised: %s */" % _safe_str(e)

        print("[decompile] completed=%s errorMsg=%s" % (
            completed,
            _safe_str(res.getErrorMessage()) if res else "n/a"))

        if not completed:
            msg = ""
            try:
                msg = res.getErrorMessage() or ""
            except Exception:
                pass
            return "/* decompile did not complete: %s */" % msg

        df = None
        try:
            df = res.getDecompiledFunction()
        except Exception as e:
            return "/* getDecompiledFunction raised: %s */" % _safe_str(e)

        if df is None:
            return "/* getDecompiledFunction returned None */"

        try:
            c = df.getC()
            return c if c else "/* getC returned empty */"
        except Exception as e:
            return "/* getC raised: %s */" % _safe_str(e)

    finally:
        try:
            di.dispose()
        except Exception:
            pass


def _collect_program_summary(script):
    p = script.currentProgram
    if p is None:
        return {}
    lang = None
    comp = None
    try:
        lang = p.getLanguage().getLanguageID().toString()
    except Exception:
        lang = None
    try:
        comp = p.getCompilerSpec().getCompilerSpecID().toString()
    except Exception:
        comp = None
    try:
        image_base = _addr_to_str(p.getImageBase())
    except Exception:
        image_base = ""
    try:
        fmt = p.getExecutableFormat()
    except Exception:
        fmt = ""
    try:
        name = p.getName()
    except Exception:
        name = ""
    return {
        "name": name,
        "language": lang,
        "compiler": comp,
        "imageBase": image_base,
        "format": fmt,
    }


def _collect_function_summary(func):
    if func is None:
        return {}
    try:
        sig = func.getPrototypeString(False, False)
    except Exception:
        sig = ""
    try:
        size = func.getBody().getNumAddresses()
    except Exception:
        size = 0
    return {
        "name": func.getName(),
        "entry": _addr_to_str(func.getEntryPoint()),
        "signature": sig,
        "size": size,
    }


def _collect_imports(script, max_items):
    p = script.currentProgram
    if p is None:
        return []
    out = []
    try:
        symtab = p.getSymbolTable()
        it = symtab.getExternalSymbols()
        while it.hasNext() and len(out) < max_items:
            s = it.next()
            out.append(_safe_str(s.getName(True)))
    except Exception:
        pass
    return out


def _collect_strings(script, max_items):
    p = script.currentProgram
    if p is None:
        return []
    out = []
    try:
        listing = p.getListing()
        data_it = listing.getDefinedData(True)
        while data_it.hasNext() and len(out) < max_items:
            d = data_it.next()
            dt = None
            try:
                dt = d.getDataType()
            except Exception:
                dt = None
            if dt is None:
                continue
            name = ""
            try:
                name = dt.getName().lower()
            except Exception:
                name = ""
            if "string" not in name:
                continue
            try:
                v = d.getValue()
                if v is None:
                    continue
                s = _safe_str(v)
            except Exception:
                continue
            s = re.sub(r"\s+", " ", s).strip()
            if not s:
                continue
            addr = _addr_to_str(d.getAddress())
            out.append("%s: %s" % (addr, s))
    except Exception:
        pass
    return out


def _collect_xrefs(script, func, max_items):
    p = script.currentProgram
    if p is None or func is None:
        return []
    out = []
    try:
        refman = p.getReferenceManager()
        entry = func.getEntryPoint()
        refs = refman.getReferencesTo(entry)
        for r in refs:
            if len(out) >= max_items:
                break
            try:
                from_addr = _addr_to_str(r.getFromAddress())
                rt = r.getReferenceType()
                kind = _safe_str(rt) if rt else ""
                out.append("%s -> %s (%s)" % (from_addr, _addr_to_str(entry), kind))
            except Exception:
                continue
    except Exception:
        pass
    return out


def collect_context(script, settings):
    p = script.currentProgram
    if p is None:
        return {
            "error": "No program is currently open.",
            "program": {},
            "location": {},
            "function": {},
            "decompile": "",
            "listingSnippet": "",
            "strings": [],
            "imports": [],
            "xrefs": [],
        }

    loc = None
    try:
        loc = script.currentLocation
    except Exception:
        loc = None

    loc_addr = None
    try:
        loc_addr = script.currentAddress
    except Exception:
        loc_addr = None

    func = None
    try:
        func = script.currentFunction
    except Exception:
        func = None
    if func is None:
        func = _get_function_at(script, loc_addr)

    disasm = ""
    try:
        b = int(getattr(settings, "disasm_lines_before", 6))
        a = int(getattr(settings, "disasm_lines_after", 10))
        disasm = _collect_disassembly_window(p, loc_addr, b, a)
    except Exception:
        disasm = ""

    decomp = ""
    if getattr(settings, "include_decompile", True):
        decomp = _decompile_function(script, func, settings.decompile_timeout_seconds)

    strings = []
    if getattr(settings, "include_strings", False):
        strings = _collect_strings(script, settings.max_strings)

    imports = []
    if getattr(settings, "include_imports", False):
        imports = _collect_imports(script, settings.max_imports)

    xrefs = []
    if getattr(settings, "include_xrefs", False):
        xrefs = _collect_xrefs(script, func, settings.max_xrefs)

    return {
        "error": "",
        "program": _collect_program_summary(script),
        "location": {
            "address": _addr_to_str(loc_addr),
            "ghidraLocation": _location_to_str(loc),
        },
        "function": _collect_function_summary(func),
        "listingSnippet": disasm,
        "decompile": decomp,
        "strings": strings,
        "imports": imports,
        "xrefs": xrefs,
    }

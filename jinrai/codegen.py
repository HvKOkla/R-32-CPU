"""
Jinrai — génération de code assembleur R-32 (v3.0).

Convention d'appel :
  - arguments : R2 (A0), R3 (A1) — max 2 paramètres
  - retour : R1 (RA)
  - R1-R3 : scratch (caller-saved, écrasés par tout appel)
  - R4-R11 : callee-saved — le CALLEE sauvegarde ce qu'il utilise (PUSH/POP)

Les variables locales vivent dans R4+ ; les temporaries d'expression au-dessus.
Le checker garantit : nb_locaux + pression_max <= 8.
"""

from checker import REG_POOL

REG = {i: f"R{i}" for i in range(16)}
UART_DATA, UART_STATUS, DEBUG_DEC = 0xF000, 0xF001, 0xF002

ESC_REV = {10: "\\n", 13: "\\r", 9: "\\t", 0: "\\0", 92: "\\\\", 34: '\\"'}


class FnCtx:
    def __init__(self, info):
        self.info = info
        self.nlocals = info.slots
        self.ntemp = 0
        self.label_id = 0

    def alloc(self):
        r = 4 + self.nlocals + self.ntemp
        self.ntemp += 1
        assert r < 4 + REG_POOL, "dépassement de pool (checker défaillant ?)"
        return r

    def free(self, r):
        """Libère r ssi c'est le temporaire du sommet (LIFO strict)."""
        lo = 4 + self.nlocals
        if lo <= r < lo + self.ntemp and r == lo + self.ntemp - 1:
            self.ntemp -= 1

    def uniq(self, prefix):
        self.label_id += 1
        return f"{prefix}_{self.info.node['name']}_{self.label_id}"

    def local_reg(self, name):
        return 4 + self.info.locals[name]["slot"]

    def param_reg(self, name):
        return 2 + self.info.params.index(name)


class CodeGen:
    def __init__(self, fns, warnings):
        self.fns = fns
        self.warnings = warnings
        self.out = []
        self.data = []
        self.lib = set()

    def emit(self, s=""):
        self.out.append(s)

    # ================= programme =================
    def generate(self, entry=True):
        """entry=True : programme standalone (émet CALL main + HALT).
        entry=False : snippet (REPL, bibliothèque) — pas de point d'entrée."""
        self.emit("; ============================================================")
        self.emit("; Généré par Jinrai — ne pas éditer à la main")
        self.emit("; Convention : args R2/R3, retour R1, R4-R11 + LR callee-saved")
        self.emit("; ============================================================")
        self.emit("")
        if entry:
            self.emit("    CALL main")
            self.emit("    HALT")
            self.emit("")
        for info in self.fns.values():
            self.gen_fn(info)
        self.emit_lib()
        self.emit("")
        for d in self.data:
            self.emit(d)
        return "\n".join(self.out) + "\n"

    def gen_fn(self, info):
        ctx = FnCtx(info)
        self.cur = ctx
        name = info.node["name"]
        self.emit(f"{name}:")
        # le callee sauvegarde TOUT ce qu'il utilise : slots + temporaries,
        # ET LR (sinon les appels imbriqués écrasent l'adresse de retour)
        nsave = info.slots + info.max_pressure
        if not info.naked:
            for i in range(nsave):
                self.emit(f"    PUSH {REG[4 + i]}")
            self.emit("    PUSH R14")
        for i, p in enumerate(info.params):  # args R2/R3 -> slots
            self.emit(f"    MOV {REG[4 + i]}, R{2 + i}")
        for s in info.node["body"]:
            self.gen_stmt(s, ctx)
        if not info.naked:
            self.emit(f"__ret_{name}:")
            self.emit("    POP R14")
            for i in reversed(range(nsave)):
                self.emit(f"    POP {REG[4 + i]}")
            self.emit("    RET")
        self.emit("")

    # ================= instructions =================
    def gen_stmt(self, s, ctx):
        tag = s["tag"]
        if tag == "decl":
            t = self.gen_expr(s["init"], ctx)
            self.emit(f"    MOV {REG[ctx.local_reg(s['name'])]}, {REG[t]}")
            ctx.free(t)
        elif tag == "assign":
            t = self.gen_expr(s["value"], ctx)
            self.emit(f"    MOV {REG[ctx.local_reg(s['name'])]}, {REG[t]}")
            ctx.free(t)
        elif tag == "if":
            t = self.gen_expr(s["cond"], ctx)
            ctx.free(t)
            l_else, l_end = ctx.uniq("else"), ctx.uniq("endif")
            self.emit(f"    CMPI {REG[t]}, 0")
            self.emit(f"    JZ {l_else}")
            for st in s["then"]:
                self.gen_stmt(st, ctx)
            self.emit(f"    JMP {l_end}")
            self.emit(f"{l_else}:")
            if s["other"] is not None:
                for st in s["other"]:
                    self.gen_stmt(st, ctx)
            self.emit(f"{l_end}:")
        elif tag == "while":
            l_top, l_end = ctx.uniq("while"), ctx.uniq("wend")
            self.emit(f"{l_top}:")
            t = self.gen_expr(s["cond"], ctx)
            ctx.free(t)
            self.emit(f"    CMPI {REG[t]}, 0")
            self.emit(f"    JZ {l_end}")
            for st in s["body"]:
                self.gen_stmt(st, ctx)
            self.emit(f"    JMP {l_top}")
            self.emit(f"{l_end}:")
        elif tag == "return":
            if s["value"] is not None:
                t = self.gen_expr(s["value"], ctx)
                self.emit(f"    MOV R1, {REG[t]}")
                ctx.free(t)
            if ctx.info.naked:
                self.emit("    RET")
            else:
                self.emit(f"    JMP __ret_{ctx.info.node['name']}")
        elif tag == "asm":
            for line in s["text"].split("\n"):
                line = line.strip()
                if not line:
                    continue
                for pname in ctx.info.params:
                    line = line.replace("{" + pname + "}", REG[ctx.param_reg(pname)])
                for lname in ctx.info.locals:
                    line = line.replace("{" + lname + "}", REG[ctx.local_reg(lname)])
                self.emit("    " + line)
        elif tag == "exprstmt":
            self.gen_call(s["expr"], ctx, want_result=False)

    # ================= expressions =================
    def gen_expr(self, e, ctx):
        t = e["tag"]
        if t == "num":
            r = ctx.alloc()
            self.emit(f"    MOV {REG[r]}, {e['val'] & 0xFFFF}")
            return r
        if t == "var":
            # invariant : tout résultat d'expression possède un temporaire
            if e["name"] in ctx.info.locals:
                src = ctx.local_reg(e["name"])
            elif e["name"] in ctx.info.params:
                src = ctx.param_reg(e["name"])
            else:
                raise AssertionError(f"variable inconnue {e['name']} (checker défaillant ?)")
            r = ctx.alloc()
            self.emit(f"    MOV {REG[r]}, {REG[src]}")
            return r
        if t == "un":
            return self.gen_unary(e, ctx)
        if t == "bin":
            return self.gen_binop(e, ctx)
        if t == "call":
            return self.gen_call(e, ctx, want_result=True)
        raise AssertionError(f"noeud inconnu {t}")

    def gen_unary(self, e, ctx):
        if e["op"] == "neg":
            t = self.gen_expr(e["e"], ctx)
            t2 = ctx.alloc()
            self.emit(f"    MOV {REG[t2]}, 0")
            self.emit(f"    SUB {REG[t2]}, {REG[t]}")
            self.emit(f"    MOV {REG[t]}, {REG[t2]}")
            ctx.free(t2)
            return t
        if e["op"] == "not":
            t = self.gen_expr(e["e"], ctx)
            l_set, l_end = ctx.uniq("not1"), ctx.uniq("not0")
            self.emit(f"    CMPI {REG[t]}, 0")
            self.emit(f"    MOV {REG[t]}, 0")
            self.emit(f"    JZ {l_set}")
            self.emit(f"    JMP {l_end}")
            self.emit(f"{l_set}:")
            self.emit(f"    MOV {REG[t]}, 1")
            self.emit(f"{l_end}:")
            return t
        raise AssertionError(f"unaire inconnu {e['op']}")

    def gen_binop(self, e, ctx):
        op = e["op"]
        if op in ("and", "or"):
            l = self.gen_expr(e["l"], ctx)
            r = self.gen_expr(e["r"], ctx)
            ins = "AND" if op == "and" else "OR"
            self.emit(f"    {ins} {REG[l]}, {REG[r]}")
            ctx.free(r)
            return l
        if op in ("*", "/", "%"):
            l = self.gen_expr(e["l"], ctx)
            r = self.gen_expr(e["r"], ctx)
            self.emit(f"    MOV R2, {REG[l]}")
            self.emit(f"    MOV R3, {REG[r]}")
            if op == "*":
                self.lib.add("__jin_mul16")
                self.emit("    CALL __jin_mul16")
            else:
                self.lib.add("__jin_div16")
                self.emit("    CALL __jin_div16")
            if op == "%":
                self.emit(f"    MOV {REG[l]}, R3")
            else:
                self.emit(f"    MOV {REG[l]}, R1")
            ctx.free(r)
            return l
        # comparaisons et + -
        l = self.gen_expr(e["l"], ctx)
        r = self.gen_expr(e["r"], ctx)
        if op == "+":
            self.emit(f"    ADD {REG[l]}, {REG[r]}")
        elif op == "-":
            self.emit(f"    SUB {REG[l]}, {REG[r]}")
        else:
            l_set, l_end = ctx.uniq("set1"), ctx.uniq("set0")
            if op == ">":
                self.emit(f"    CMP {REG[r]}, {REG[l]}")   # b-a : N si b<a i.e. a>b
            elif op == "<=":
                self.emit(f"    CMP {REG[r]}, {REG[l]}")   # N si b<a → a<=b faux
            else:
                self.emit(f"    CMP {REG[l]}, {REG[r]}")
            self.emit(f"    MOV {REG[l]}, 0")
            if op == "==":
                self.emit(f"    JNZ {l_end}")
            elif op == "!=":
                self.emit(f"    JZ {l_end}")
            elif op in ("<", ">"):
                self.emit(f"    JN {l_set}")
                self.emit(f"    JMP {l_end}")
                self.emit(f"{l_set}:")
                self.emit(f"    MOV {REG[l]}, 1")
                self.emit(f"{l_end}:")
                ctx.free(r)
                return l
            else:  # <= >= : faux quand N=1
                self.emit(f"    JN {l_end}")
            self.emit(f"    MOV {REG[l]}, 1")
            self.emit(f"{l_end}:")
        ctx.free(r)
        return l

    def gen_call(self, e, ctx, want_result):
        """Évalue les args une seule fois, dispatche vers le bon émetteur."""
        name = e["name"]
        # print(str), addr(symbole) et trap(symbole) : pas d'évaluation d'expr
        if (name == "print" and e["args"] and e["args"][0]["tag"] == "str") \
                or name in ("addr", "trap"):
            arg_regs = [None] * len(e["args"])
        else:
            arg_regs = [self.gen_expr(a, ctx) for a in e["args"]]
        result = self._dispatch(name, e, arg_regs, ctx, want_result)
        # les fonctions Jinrai libèrent leurs args elles-mêmes (avant le CALL) ;
        # ici : libération pour les builtins (sauf si l'arg porte le résultat)
        if name not in self.fns:
            for ar in reversed(arg_regs):
                if ar is not None and (result is None or ar != result):
                    ctx.free(ar)
        return result

    def _dispatch(self, name, e, arg_regs, ctx, want_result):
        if name == "peek":
            t = arg_regs[0]
            self.emit(f"    LOAD_IND {REG[t]}, {REG[t]}")
            return t
        if name == "addr":
            t = ctx.alloc()
            self.emit(f"    MOVL {REG[t]}, {e['args'][0]['name']}")
            return t
        if name == "getc":
            t = ctx.alloc()
            l_poll = ctx.uniq("getc")
            self.emit(f"{l_poll}:")
            self.emit(f"    LOAD {REG[t]}, {hex(UART_STATUS)}")
            self.emit(f"    CMPI {REG[t]}, 0")
            self.emit(f"    JZ {l_poll}")
            self.emit(f"    LOAD {REG[t]}, {hex(UART_DATA)}")
            return t
        if name == "read_dec":
            self.lib.add("__jin_read_dec")
            self.emit("    CALL __jin_read_dec")
            if want_result:
                t = ctx.alloc()
                self.emit(f"    MOV {REG[t]}, R1")
                return t
            return None
        if name == "poke":
            self.emit(f"    STORE_IND {REG[arg_regs[1]]}, {REG[arg_regs[0]]}")
            return None
        if name == "putc":
            self.emit(f"    STORE {REG[arg_regs[0]]}, {hex(UART_DATA)}")
            return None
        if name == "print_dec":
            # le port debug 0xF002 affiche la valeur en décimal nativement
            self.emit(f"    STORE {REG[arg_regs[0]]}, {hex(DEBUG_DEC)}")
            return None
        if name == "print":
            chars = e["args"][0]["chars"]
            s = "".join(ESC_REV.get(c, chr(c)) for c in chars)
            lbl = f"__jstr_{len(self.data)}"
            self.data.append(f'{lbl}: .string "{s}"')
            l_loop, l_done = ctx.uniq("pstr"), ctx.uniq("pdone")
            self.emit(f"    MOVL R2, {lbl}")
            self.emit(f"{l_loop}:")
            self.emit("    LOAD_IND R1, R2")
            self.emit("    CMPI R1, 0")
            self.emit(f"    JZ {l_done}")
            self.emit(f"    STORE R1, {hex(UART_DATA)}")
            self.emit("    INC R2")
            self.emit(f"    JMP {l_loop}")
            self.emit(f"{l_done}:")
            return None
        if name == "halt":
            self.emit("    HALT")
            return None
        if name == "trap":
            self.emit(f"    TRAP {e['args'][0]['name']}")
            return None
        if name == "iret":
            self.emit("    IRET")
            return None
        if name == "asm":
            return None  # traité comme statement ; jamais atteint ici
        # appel utilisateur : arg_regs évalués -> R2/R3, libérés AVANT le CALL
        # (LIFO strict) pour que le résultat ne soit pas alloué par-dessus eux
        for i, ar in enumerate(arg_regs):
            self.emit(f"    MOV R{2 + i}, {REG[ar]}")
        for ar in reversed(arg_regs):
            if ar is not None:
                ctx.free(ar)
        self.emit(f"    CALL {name}")
        if want_result:
            t = ctx.alloc()
            self.emit(f"    MOV {REG[t]}, R1")
            return t
        return None

    # ================= bibliothèque =================
    def emit_lib(self):
        if "__jin_mul16" in self.lib:
            self.emit("__jin_mul16:            ; R2*R3 -> R1 (additions répétées)")
            self.emit("    PUSH R4")
            self.emit("    PUSH R5")
            self.emit("    MOV R4, R2")
            self.emit("    MOV R5, R3")
            self.emit("    MOV R1, 0")
            self.emit("__jin_mul_loop:")
            self.emit("    CMPI R5, 0")
            self.emit("    JZ __jin_mul_done")
            self.emit("    ADD R1, R4")
            self.emit("    DEC R5")
            self.emit("    JMP __jin_mul_loop")
            self.emit("__jin_mul_done:")
            self.emit("    POP R5")
            self.emit("    POP R4")
            self.emit("    RET")
            self.emit("")
        if "__jin_div16" in self.lib:
            self.emit("__jin_div16:            ; R2/R3 -> R1 (quotient), R3 (reste)")
            self.emit("    PUSH R4")
            self.emit("    PUSH R5")
            self.emit("    MOV R4, R2")
            self.emit("    MOV R5, R3")
            self.emit("    MOV R1, 0")
            self.emit("    CMPI R5, 0")
            self.emit("    JZ __jin_div_done    ; div par 0 -> quotient 0, reste R2")
            self.emit("__jin_div_loop:")
            self.emit("    CMP R4, R5")
            self.emit("    JN __jin_div_done")
            self.emit("    SUB R4, R5")
            self.emit("    INC R1")
            self.emit("    JMP __jin_div_loop")
            self.emit("__jin_div_done:")
            self.emit("    MOV R3, R4")
            self.emit("    POP R5")
            self.emit("    POP R4")
            self.emit("    RET")
            self.emit("")
        if "__jin_read_dec" in self.lib:
            self.emit("__jin_read_dec:         ; -> R1 : nombre tapé au clavier")
            self.emit("    PUSH R4")
            self.emit("    PUSH R5")
            self.emit("    MOV R1, 0")
            self.emit("__jin_rd_loop:")
            self.emit(f"    LOAD R4, {hex(UART_STATUS)}")
            self.emit("    CMPI R4, 0")
            self.emit("    JZ __jin_rd_loop")
            self.emit(f"    LOAD R4, {hex(UART_DATA)}")
            self.emit("    CMPI R4, 13")
            self.emit("    JZ __jin_rd_done")
            self.emit("    CMPI R4, 48")
            self.emit("    JN __jin_rd_loop")
            self.emit("    CMPI R4, 58")
            self.emit("    JN __jin_rd_digit")
            self.emit("    JMP __jin_rd_loop")
            self.emit("__jin_rd_digit:")
            self.emit("    MOV R2, 48")
            self.emit("    SUB R4, R2")
            self.emit("    MOV R5, R1")   # R5 : temporaire (caller-saved, ok ici)
            self.emit("    MOV R2, 1")
            self.emit("    SHL R1, R2")   # *2
            self.emit("    SHL R5, R2")   # *2
            self.emit("    SHL R5, R2")   # *4
            self.emit("    SHL R5, R2")   # *8
            self.emit("    ADD R1, R5")   # *10
            self.emit("    ADD R1, R4")
            self.emit("    JMP __jin_rd_loop")
            self.emit("__jin_rd_done:")
            self.emit("    POP R5")
            self.emit("    POP R4")
            self.emit("    RET")
            self.emit("")


def generate(program, fns, warnings, entry=True):
    return CodeGen(fns, warnings).generate(entry=entry)

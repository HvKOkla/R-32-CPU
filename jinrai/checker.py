"""
Jinrai — checker impitoyable.

Règles (toutes bloquantes, sauf avertissements) :
  JR0001 variable déjà déclarée dans la fonction
  JR0002 nom inconnu
  JR0003 variable utilisée avant initialisation
  JR0004 assignation d'une variable 'let' (immutable)
  JR0005 fonction/builtin inconnu(e)
  JR0006 mauvais nombre d'arguments
  JR0007 littéral hors plage (-32768..65535)
  JR0008 division par zéro constante
  JR0009 code inaccessible après return
  JR0010 fonction à valeur : le corps doit se terminer par return
  JR0011 pression de registres > 8 (R4-R11 : locaux + temporaries)
  JR0012 fonction naked : seuls asm/iret/halt autorisés
  JR0013 TRAP vers une fonction qui n'est pas naked

Avertissements (--pedantic les promeut en erreurs) :
  JR2001 variable locale jamais utilisée
  JR2002 paramètre jamais utilisé
  JR2003 fonction jamais appelée
  JR2004 résultat d'appel ignoré
"""

from lexer import JinraiError

# builtins : nom -> (nb_args, retourne_valeur, position)
BUILTINS = {
    "peek":      (1, True,  "expr"),
    "getc":      (0, True,  "expr"),
    "read_dec":  (0, True,  "expr"),
    "addr":      (1, True,  "expr"),
    "poke":      (2, False, "stmt"),
    "putc":      (1, False, "stmt"),
    "print":     (1, False, "stmt"),
    "print_dec": (1, False, "stmt"),
    "halt":      (0, False, "stmt"),
    "trap":      (1, False, "stmt"),
    "iret":      (0, False, "stmt"),
    "asm":       (1, False, "stmt"),
}

REG_POOL = 8  # R4..R11


class FnInfo:
    def __init__(self, node):
        self.node = node
        self.params = node["params"]
        self.locals = {}        # name -> dict(slot, mutable, used, line)
        self.max_pressure = 1
        self.has_value_return = False
        self.called = False

    @property
    def naked(self):
        return self.node["naked"]

    @property
    def slots(self):
        return len(self.locals)


class Checker:
    def __init__(self, program, pedantic=False):
        self.program = program
        self.pedantic = pedantic
        self.fns = {}
        self.warnings = []
        for f in program["fns"]:
            if f["name"] in self.fns:
                raise JinraiError("JR0014", f"fonction '{f['name']}' déjà définie", f["line"], 0)
            self.fns[f["name"]] = FnInfo(f)

    def warn(self, code, msg, line):
        if self.pedantic:
            raise JinraiError(code, msg + " (--pedantic)", line, 0)
        self.warnings.append(f"avertissement[{code}] : {msg} (ligne {line})")

    # ---------- évaluation constante ----------
    def const_eval(self, e):
        t = e["tag"]
        if t == "num":
            return e["val"]
        if t == "un":
            v = self.const_eval(e["e"])
            if v is None:
                return None
            return -v if e["op"] == "neg" else (0 if v != 0 else 1)
        if t == "bin":
            a, b = self.const_eval(e["l"]), self.const_eval(e["r"])
            if a is None or b is None:
                return None
            op = e["op"]
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op in ("/", "%"):
                if b == 0:
                    raise JinraiError("JR0008", "division par zéro constante", e["line"], 0)
                return a // b if op == "/" else a % b
            if op == "and":
                return a & b
            if op == "or":
                return a | b
            if op == "==":
                return int(a == b)
            if op == "!=":
                return int(a != b)
            if op == "<":
                return int(a < b)
            if op == ">":
                return int(a > b)
            if op == "<=":
                return int(a <= b)
            if op == ">=":
                return int(a >= b)
        return None

    def check_literal_range(self, e):
        if e["tag"] == "num":
            v = e["val"]
            if not (-32768 <= v <= 65535):
                raise JinraiError(
                    "JR0007",
                    f"littéral {v} hors plage (-32768..65535, i16)",
                    e["line"], 0)
        for k in ("l", "r", "e"):
            if k in e:
                self.check_literal_range(e[k])
        for a in e.get("args", []):
            self.check_literal_range(a)
        if "init" in e:
            self.check_literal_range(e["init"])
        if "value" in e and e["value"] is not None:
            self.check_literal_range(e["value"])
        if "cond" in e:
            self.check_literal_range(e["cond"])

    # ---------- pression de registres (Sethi-Ullberg simplifié) ----------
    def pressure(self, e):
        t = e["tag"]
        if t in ("num", "var", "str"):
            return 1
        if t == "un":
            return self.pressure(e["e"])
        if t == "bin":
            pl, pr = self.pressure(e["l"]), self.pressure(e["r"])
            return pl + 1 if pl == pr else max(pl, pr)
        if t == "call":
            p = max((self.pressure(a) for a in e["args"]), default=1)
            if e["name"] in ("peek", "getc", "read_dec", "addr"):
                return max(p, 1) if e["name"] == "peek" else 1
            return p + 1
        return 1

    def note_expr(self, e):
        self.max_pressure = max(self.max_pressure, self.pressure(e))
        self.check_literal_range(e)

    # ---------- analyse ----------
    def check(self):
        for info in self.fns.values():
            self.check_fn(info)
        for name, info in self.fns.items():
            if name != "main" and not info.called:
                self.warn("JR2003", f"fonction '{name}' jamais appelée", info.node["line"])
        return self.fns, self.warnings

    def check_fn(self, info):
        node = info.node
        if len(info.params) > 2:
            raise JinraiError("JR0015",
                              f"fonction '{node['name']}' : max 2 paramètres "
                              f"(convention R2, R3)", node["line"], 0)
        if info.naked:
            allowed = {"asm"}
            for s in node["body"]:
                ok = (s["tag"] == "asm"
                      or (s["tag"] == "exprstmt" and s["expr"]["tag"] == "call"
                          and s["expr"]["name"] in ("iret", "halt")))
                if not ok:
                    raise JinraiError(
                        "JR0012",
                        f"fonction naked '{node['name']}' : seuls asm(\"...\"), "
                        f"iret() et halt() sont autorisés (ligne {s['line']})",
                        s["line"], 0)
            return

        self.cur = info
        self.max_pressure = 1
        # les paramètres occupent les premiers slots (mutables : copies locales)
        for p in info.params:
            info.locals[p] = {"slot": info.slots, "mutable": True,
                              "used": False, "line": node["line"]}
        self.check_block(node["body"])
        if info.has_value_return:
            last = node["body"][-1] if node["body"] else None
            if not last or last["tag"] != "return":
                raise JinraiError(
                    "JR0010",
                    f"fonction '{node['name']}' retourne une valeur : "
                    f"la dernière instruction doit être return",
                    node["line"], 0)
        info.max_pressure = self.max_pressure
        need = info.slots + info.max_pressure
        if need > REG_POOL:
            raise JinraiError(
                "JR0011",
                f"fonction '{node['name']}' : {need} registres nécessaires "
                f"({info.slots} locaux + {info.max_pressure} temporaries), "
                f"{REG_POOL} disponibles (R4-R11). "
                f"Découpe l'expression ou la fonction.",
                node["line"], 0)
        for pname in info.params:
            p = info.locals.get(pname)
            if p and not p["used"]:
                self.warn("JR2002", f"paramètre '{pname}' jamais utilisé",
                          p["line"])
        for lname, loc in info.locals.items():
            if lname in info.params:
                continue  # déjà signalé
            if not loc["used"]:
                self.warn("JR2001", f"variable '{lname}' jamais utilisée",
                          loc["line"])

    def lookup(self, name, line):
        loc = self.cur.locals.get(name)
        if loc is None:
            raise JinraiError("JR0002", f"'{name}' inconnu dans cette fonction",
                              line, 0)
        return loc

    def check_block(self, stmts):
        dead = False
        for s in stmts:
            if dead:
                raise JinraiError("JR0009", "code inaccessible après return",
                                  s["line"], 0)
            self.check_stmt(s)
            if s["tag"] == "return":
                dead = True

    def check_stmt(self, s):
        tag = s["tag"]
        if tag == "decl":
            if s["name"] in self.cur.locals:
                raise JinraiError("JR0001",
                                  f"'{s['name']}' déjà déclarée (pas de shadowing)",
                                  s["line"], 0)
            self.check_expr(s["init"])
            self.cur.locals[s["name"]] = {
                "slot": self.cur.slots, "mutable": s["mutable"],
                "used": False, "line": s["line"],
            }
        elif tag == "assign":
            loc = self.lookup(s["name"], s["line"])
            if not loc["mutable"]:
                raise JinraiError(
                    "JR0004",
                    f"'{s['name']}' est immutable (déclarée avec let) — utilise var",
                    s["line"], 0)
            self.check_expr(s["value"])
        elif tag == "if":
            self.check_expr(s["cond"])
            self.check_block(s["then"])
            if s["other"] is not None:
                self.check_block(s["other"])
        elif tag == "while":
            self.check_expr(s["cond"])
            self.check_block(s["body"])
        elif tag == "return":
            if s["value"] is not None:
                self.check_expr(s["value"])
                self.cur.has_value_return = True
        elif tag == "asm":
            pass  # le contenu est verbatim ; l'assembleur tranchera
        elif tag == "exprstmt":
            self.check_expr(s["expr"], as_stmt=True)

    def check_expr(self, e, as_stmt=False):
        t = e["tag"]
        if t == "num":
            pass
        elif t == "str":
            if e.get("_ctx") != "print":
                raise JinraiError("JR0016",
                                  "chaîne littérale : seul print(\"...\") l'accepte",
                                  e["line"], 0)
        elif t == "var":
            loc = self.lookup(e["name"], e["line"])
            loc["used"] = True
            self.note_expr(e)
        elif t == "un":
            self.check_expr(e["e"])
        elif t == "bin":
            self.check_expr(e["l"])
            self.check_expr(e["r"])
            v = self.const_eval(e)  # JR0007 (hors plage) / JR0008 (div par 0)
            if v is not None and not (-32768 <= v <= 65535):
                raise JinraiError(
                    "JR0007",
                    f"expression constante = {v}, hors plage i16 (-32768..65535)",
                    e["line"], 0)
        elif t == "call":
            self.check_call(e, as_stmt)
        self.note_expr(e)

    def check_call(self, e, as_stmt):
        name = e["name"]
        if name in BUILTINS:
            arity, has_ret, pos = BUILTINS[name]
            if len(e["args"]) != arity:
                raise JinraiError("JR0006",
                                  f"'{name}' attend {arity} argument(s), "
                                  f"reçu {len(e['args'])}", e["line"], 0)
            if pos == "stmt" and not as_stmt:
                raise JinraiError("JR0017",
                                  f"'{name}' est une instruction, pas une expression",
                                  e["line"], 0)
            if name == "print" and e["args"] and e["args"][0]["tag"] == "str":
                e["args"][0]["_ctx"] = "print"
            for a in e["args"]:
                if name in ("addr", "trap") and a is e["args"][0]:
                    continue  # référence de symbole, pas une variable
                if a["tag"] == "str" and name != "print":
                    raise JinraiError("JR0016",
                                      f"'{name}' n'accepte pas de chaîne littérale",
                                      a["line"], 0)
                self.check_expr(a)
            if name == "print" and e["args"] and e["args"][0]["tag"] != "str":
                raise JinraiError("JR0016", "print attend une chaîne : print(\"...\")",
                                  e["line"], 0)
            if name == "addr":
                target = e["args"][0]
                if target["tag"] != "var":
                    raise JinraiError("JR0018",
                                      "addr(x) : x doit être un nom de fonction "
                                      "ou de variable", e["line"], 0)
                n = target["name"]
                if n not in self.fns and n not in self.cur.locals and n not in self.cur.params:
                    raise JinraiError("JR0002", f"'{n}' inconnu", e["line"], 0)
            if name == "trap":
                target = e["args"][0]
                if target["tag"] != "var":
                    raise JinraiError("JR0013",
                                      "trap(handler) : handler doit être une fonction",
                                      e["line"], 0)
                info = self.fns.get(target["name"])
                if info is None:
                    raise JinraiError("JR0005", f"fonction '{target['name']}' inconnue",
                                      e["line"], 0)
                if not info.naked:
                    raise JinraiError(
                        "JR0013",
                        f"trap('{target['name']}') : la fonction doit être 'naked' "
                        f"(elle se termine par iret())", e["line"], 0)
            if as_stmt and has_ret and name in ("peek", "getc", "read_dec"):
                self.warn("JR2004", f"résultat de '{name}()' ignoré", e["line"])
            return
        info = self.fns.get(name)
        if info is None:
            raise JinraiError("JR0005", f"fonction '{name}' inconnue", e["line"], 0)
        if len(e["args"]) != len(info.params):
            raise JinraiError("JR0006",
                              f"'{name}' attend {len(info.params)} argument(s), "
                              f"reçu {len(e['args'])}", e["line"], 0)
        for a in e["args"]:
            self.check_expr(a)
        info.called = True
        if as_stmt and info.has_value_return:
            self.warn("JR2004", f"résultat de '{name}()' ignoré", e["line"])


def check(program, pedantic=False):
    c = Checker(program, pedantic)
    return c.check()

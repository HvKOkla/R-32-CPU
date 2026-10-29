#!/usr/bin/env python3
"""
jrepl.py — REPL interactif Jinrai pour la VM R-32 (le "JIT" de l'écosystème).

Chaque ligne tapée est compilée (~5 ms) puis exécutée SUR une VM persistante :
  - les expressions affichent leur valeur (comme dans Python)
  - les `fn` définies restent appelables dans les lignes suivantes
  - la mémoire (poke/peek, VRAM...) survit d'une ligne à l'autre
  - le code compilé se charge à partir de 0x1000 (poke sous 0x1000 = données sûres)

Commandes spéciales : :help :quit :regs :flags :mem A [n] :base :reset

Usage : python tools/jrepl.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "jinrai"))

from lexer import JinraiError          # noqa: E402
from parser import parse              # noqa: E402
from checker import check             # noqa: E402
from codegen import generate          # noqa: E402
from assembler import R32Assembler    # noqa: E402
from vm import R32VM                  # noqa: E402

BASE = 0x1000
JUMPS = ("JZ", "JNZ", "JN", "JC", "JV", "JMP", "CALL", "TRAP")

INTRO = """\
R-32 Jinrai REPL — chaque ligne compile en ~5 ms et tourne sur la VM.
  expression      → évaluée, sa valeur s'affiche     ex: 6 * 7
  instruction     → exécutée                         ex: poke(0x200, 42)
  fn ... { ... }  → définie pour la session          ex: fn dbl(x) { return x * 2 }
  :help pour les commandes spéciales, :quit pour sortir.
Le code se charge à partir de 0x1000 — vos données (poke) vivent sous 0x1000.
"""


class Repl:
    def __init__(self):
        self.reset()

    def reset(self):
        self.vm = R32VM()
        self.labels = {}        # labels absolus cumulés entre les snippets
        self.known = {}         # signatures cumulées : nom -> (arity, has_ret, naked)
        self.here = BASE        # prochaine adresse de chargement
        self.n = 0              # compteur de snippets

    # ---------- assemblage avec labels persistants ----------
    def assemble_snippet(self, lines):
        """Même logique que R32Assembler.assemble_lines, mais la table des
        labels est PERSISTANTE : un snippet peut appeler les fn des
        snippets précédents."""
        # les routines lib (__jin_*) déjà chargées ne sont pas ré-émises
        filtered, skip = [], False
        for ln in lines:
            s = ln.strip()
            lbl = s.split(":", 1)[0].strip() if ":" in s else ""
            if not skip and ":" in s and not s.startswith(".") \
                    and lbl in self.labels and lbl.startswith("__jin"):
                skip = True
                continue
            if skip:
                if s.split(";", 1)[0].strip() == "RET":
                    skip = False
                continue
            filtered.append(ln)
        lines = filtered

        asm = R32Assembler()
        fresh = asm._collect_labels(lines)
        merged = dict(self.labels)
        for k, v in fresh.items():
            if k in merged and merged[k] != v + self.here:
                raise ValueError(f"label '{k}' déjà défini")
            merged[k] = v + self.here

        asm.constants = {}
        for ln, raw in enumerate(lines, 1):
            l = asm._clean(raw)
            if not l:
                continue
            parts = asm._tokenize(l)
            if parts[0].lower() == ".equ":
                asm.constants[parts[1]] = asm._parse_number(parts[2], ln, 0xFFFF)

        buffer = {}
        pc = 0
        for ln, raw in enumerate(lines, 1):
            l = asm._clean(raw)
            if not l:
                continue
            _, l = asm._strip_label(l)
            if not l:
                continue
            parts = asm._tokenize(l)
            h = parts[0].lower()
            if h == ".equ":
                continue
            if h == ".org":
                pc = asm._parse_number(parts[1], ln, 0xFFFF)
                continue
            if h == ".align":
                a = 1 << asm._parse_number(parts[1], ln, 15)
                pc = (pc + a - 1) & ~(a - 1)
                continue
            if h in (".ascii", ".string"):
                for v in asm._string_words(l, ln):
                    buffer[pc] = v
                    pc += 1
                continue
            if h == ".word":
                for t in parts[1:]:
                    buffer[pc] = asm._parse_number(t, ln, 0xFFFF)
                    pc += 1
                continue
            instr = asm._emit(l, ln, merged)
            for i, w in enumerate(instr):
                buffer[pc + i] = w
            pc += len(instr)

        self.labels = merged
        if not buffer:
            return []
        code = [0] * (max(buffer) + 1)
        for a, w in buffer.items():
            code[a] = w
        return code

    # ---------- exécution ----------
    def execute(self, src):
        """Compile et exécute un snippet. Renvoie (kind, payload)."""
        kind = "stmt"
        call_name = None
        if src.lstrip().startswith(("fn ", "naked fn")):
            lines = src.splitlines()
        else:
            # expression ? → afficher la valeur ; sinon instruction silencieuse
            self.n += 1
            call_name = f"__repl_{self.n}"
            wrapped = (f"fn {call_name}() {{\n"
                       f"  var __jr = ({src})\n"
                       f"  print_dec(__jr)\n"
                       f"}}")
            try:
                prog = parse(wrapped, need_main=False)
                check(prog, known=self.known)
                src = wrapped
                kind = "expr"
            except JinraiError:
                src = f"fn {call_name}() {{\n{src}\n}}"

        prog = parse(src, need_main=False)
        fns, warns = check(prog, known=self.known)
        asm_text = generate(prog, fns, warns, entry=False)

        # mémoriser les signatures définies pour les snippets suivants
        for name, info in fns.items():
            if not name.startswith("__repl_"):
                self.known[name] = (len(info.params), info.has_value_return,
                                    info.naked)

        lines = asm_text.splitlines()
        if call_name is not None:
            # trailer : appeler le snippet puis rendre la main (POP R0 équilibre
            # le CALL ; HALT arrête la VM proprement)
            lines += [f"CALL {call_name}", "POP R0", "HALT"]

        code = self.assemble_snippet(lines)
        if not code:
            return "def", None

        base = self.here
        self.vm.mem.load_program(code, base)
        self.here = base + len(code)

        if call_name is not None:
            self.vm.registers[13] = self.vm.mem.STACK_TOP   # SP propre
            self.vm.pc = base
            self.vm.halted = False
            try:
                self.vm.run()
            except Exception as e:
                return "error", str(e)
        elif code:
            return "def", None
        return kind, None

    # ---------- commandes spéciales ----------
    def cmd(self, line):
        parts = line[1:].split()
        c = parts[0] if parts else ""
        if c in ("q", "quit"):
            return False
        if c == "help":
            print(":quit  :regs  :flags  :mem A [n]  :base (adresse de chargement)"
                  "  :reset (nouvelle VM)")
        elif c == "regs":
            r = self.vm.registers
            for row in range(4):
                print("  ".join(f"R{i:2d}={r[i]:5d}" for i in range(row * 4, row * 4 + 4)))
            print(f"PC={self.vm.pc:#06x}  SP={r[13]:#06x}")
        elif c == "flags":
            print(self.vm.flags, " in_irq =", self.vm.in_irq)
        elif c == "mem":
            a = int(parts[1], 16) if parts[1].lower().startswith("0x") else int(parts[1])
            n = int(parts[2]) if len(parts) > 2 else 8
            for i in range(0, n, 8):
                vals = [self.vm.mem.read(a + i + j) for j in range(min(8, n - i))]
                print(f"{a + i:#06x}: " + " ".join(f"{v:04x}" for v in vals))
        elif c == "base":
            print(f"prochain chargement : {self.here:#06x}"
                  f"  ({len(self.labels)} labels connus)")
        elif c == "reset":
            self.reset()
            print("VM réinitialisée.")
        else:
            print(f"commande inconnue :{c} (:help)")
        return True

    # ---------- boucle ----------
    def loop(self):
        print(INTRO)
        buf = []
        while True:
            try:
                line = input("... " if buf else "jinrai> ")
            except (EOFError, KeyboardInterrupt):
                print("\nbye.")
                return
            s = line.strip()
            if not s:
                continue
            if not buf and s.startswith(":"):
                if not self.cmd(s):
                    return
                continue
            buf.append(line)
            if buf[0].lstrip().startswith(("fn ", "naked fn")) \
                    and (s.count("{") > s.count("}")):
                continue                     # définition multi-lignes : on attend la suite
            src = "\n".join(buf)
            buf = []
            try:
                kind, err = self.execute(src)
                if kind == "error":
                    print(f"erreur d'exécution : {err}")
                elif kind == "def":
                    print("(défini)")
            except (JinraiError, ValueError) as e:
                print(e, end="" if str(e).endswith("\n") else "\n")
            except Exception as e:           # codegen / assembleur
                print(f"erreur : {e}")


def main():
    repl = Repl()
    repl.loop()


if __name__ == "__main__":
    main()

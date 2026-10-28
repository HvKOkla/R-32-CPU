#!/usr/bin/env python3
"""
r32dbg.py — débogueur interactif pour la VM R-32 v3.0.

Usage : python tools/r32dbg.py build/fibonacci.hex

Commandes :
  load <fichier>   recharge un programme (.hex ou .bin)
  run              exécute jusqu'au HALT ou à un breakpoint
  step [n]         exécute n instructions (défaut 1)
  break <adresse>  pose un breakpoint (adresse de mot : 42 ou 0x2a)
  breaks           liste les breakpoints
  del <adresse>    retire un breakpoint
  regs             affiche R0-R15 et PC
  flags            affiche Z N C V
  mem <adr> [n]    affiche n mots en mémoire (défaut 8)
  set R5 42        écrit un registre ; set mem 0x40 7 écrit la mémoire
  disas [adr] [n]  désassemble n instructions (défaut 8, autour du PC)
  quit             sortie

Note : pendant run/step, l'entrée clavier du programme (READ/UART)
renvoie EOF — utilisez 'set' pour préparer les entrées.
"""

import builtins
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from vm import R32VM          # noqa: E402
from disasm import disasm     # noqa: E402
from isa import FLAG_Z, FLAG_N, FLAG_C, FLAG_V  # noqa: E402


def parse_num(tok):
    return int(tok, 16) if tok.lower().startswith("0x") else int(tok)


class Debugger:
    def __init__(self):
        self.vm = R32VM()
        self.breaks = set()
        self._orig_input = builtins.input

    # --- entrée du programme : EOF pendant l'exécution ---
    def _no_input(self):
        raise EOFError()

    def load(self, path):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
        from disasm import load_words
        words = load_words(path)
        self.vm = R32VM()
        self.vm.load_program(words)
        self.breaks = set()
        print(f"chargé : {len(words)} mots, PC=0x0000")

    def _step_one(self):
        """Exécute 1 pas ; renvoie 'brk' si breakpoint avant l'instruction."""
        if self.vm.pc in self.breaks:
            return "brk"
        return "run" if self.vm.step() else "halt"

    def run(self):
        builtins.input = self._no_input
        try:
            while True:
                state = self._step_one()
                if state == "brk":
                    print(f"** breakpoint à {hex(self.vm.pc)} **")
                    return
                if state == "halt":
                    print("** HALT — programme terminé **")
                    return
        finally:
            builtins.input = self._orig_input

    def step(self, n):
        builtins.input = self._no_input
        try:
            for _ in range(n):
                state = self._step_one()
                if state == "brk":
                    print(f"** breakpoint à {hex(self.vm.pc)} **")
                    return
                if state == "halt":
                    print("** HALT **")
                    return
        finally:
            builtins.input = self._orig_input
        self.show_regs()

    def show_regs(self):
        r = self.vm.registers
        for row in range(4):
            print("  ".join(f"R{i:2d}={r[i]:5d} (0x{r[i]:04x})"
                            for i in range(row * 4, row * 4 + 4)))
        print(f"PC={self.vm.pc:#06x}  SP={r[13]:#06x}  LR={r[14]:#06x}")

    def show_flags(self):
        f = self.vm.flags
        print(f"Z={f[FLAG_Z]} N={f[FLAG_N]} C={f[FLAG_C]} V={f[FLAG_V]}"
              f"  in_irq={self.vm.in_irq}")

    def show_mem(self, addr, n):
        for i in range(0, n, 8):
            chunk = [self.vm.mem.read(addr + i + j) for j in range(min(8, n - i))]
            print(f"{addr + i:#06x}: " + " ".join(f"{w:04x}" for w in chunk))

    def show_disas(self, addr, n):
        words = [self.vm.mem.read(addr + i) for i in range(n * 2 + 2)]
        text = disasm(words).splitlines()
        base = len([l for l in text if not l.strip() or l.startswith(";")]) - 1
        for line in text:
            if line.startswith(";"):
                continue
            print(("-> " if False else "   ") + line)

    def repl(self):
        print("r32dbg — débogueur R-32 v3.0 (help : les commandes sont dans l'en-tête)")
        while True:
            try:
                cmd = input("r32dbg> ").strip().split()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not cmd:
                continue
            op = cmd[0]
            try:
                if op in ("quit", "exit", "q"):
                    break
                elif op == "load":
                    self.load(cmd[1])
                elif op == "run":
                    self.run()
                elif op == "step":
                    self.step(int(cmd[1]) if len(cmd) > 1 else 1)
                elif op == "break":
                    self.breaks.add(parse_num(cmd[1]))
                    print(f"breakpoint à {hex(parse_num(cmd[1]))}")
                elif op == "breaks":
                    print("breakpoints:", sorted(hex(b) for b in self.breaks))
                elif op == "del":
                    self.breaks.discard(parse_num(cmd[1]))
                elif op == "regs":
                    self.show_regs()
                elif op == "flags":
                    self.show_flags()
                elif op == "mem":
                    self.show_mem(parse_num(cmd[1]), parse_num(cmd[2]) if len(cmd) > 2 else 8)
                elif op == "set":
                    if cmd[1].lower().startswith("r"):
                        self.vm.registers[parse_num(cmd[1][1:])] = parse_num(cmd[2]) & 0xFFFF
                    else:
                        self.vm.mem.write(parse_num(cmd[2]), parse_num(cmd[3]))
                elif op == "disas":
                    addr = parse_num(cmd[1]) if len(cmd) > 1 else self.vm.pc
                    self.show_disas(addr, parse_num(cmd[2]) if len(cmd) > 2 else 8)
                else:
                    print(f"commande inconnue : {op}")
            except (IndexError, ValueError) as e:
                print(f"usage invalide ({e})")


def main():
    dbg = Debugger()
    if len(sys.argv) > 1:
        dbg.load(sys.argv[1])
    dbg.repl()


if __name__ == "__main__":
    main()

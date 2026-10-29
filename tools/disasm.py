#!/usr/bin/env python3
"""
disasm.py — désassembleur R-32 v3.0.

Convertit un programme (.bin mots 16 bits little-endian, ou .hex un mot
par ligne) en source assembleur .r32.

Propriété de round-trip : pour tout binaire produit par l'assembleur,
    assemble(disasm(b)) == b        (bit à bit)

Usage : python tools/disasm.py build/fibonacci.hex [-o sortie.r32]
"""

import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from isa import OPCODES, INSTR_SIZE, OP_MOVRR  # noqa: E402

NAME = {v: k for k, v in OPCODES.items() if k != "MOVL"}
NAME[OP_MOVRR] = "MOV"  # affiché comme MOV (l'assembleur émet MOVRR)

# classification PAR OPCODE (0x01 MOV-imm et 0x1C MOVRR ne se confondent pas)
OPCLASS = {}
for _n in ("HALT", "RET", "NOP", "IRET"):
    OPCLASS[OPCODES[_n]] = "noarg"
for _n in ("INC", "DEC", "PUSH", "POP"):
    OPCLASS[OPCODES[_n]] = "reg1"
for _n in ("MOV", "CMPI"):
    OPCLASS[OPCODES[_n]] = "regimm"
for _n in ("ADD", "SUB", "CMP", "AND", "OR", "XOR", "SHL", "SHR",
           "LOAD_IND", "STORE_IND"):
    OPCLASS[OPCODES[_n]] = "regreg"
OPCLASS[OP_MOVRR] = "regreg"
for _n in ("JMP", "JZ", "JNZ", "JN", "JC", "JV", "CALL", "TRAP"):
    OPCLASS[OPCODES[_n]] = "jump"
for _n in ("LOAD", "STORE"):
    OPCLASS[OPCODES[_n]] = "mem"

NOARG = {"HALT", "RET", "NOP", "IRET"}
REG1 = {"INC", "DEC", "PUSH", "POP"}
REGIMM = {"MOV", "CMPI"}
REGREG = {"ADD", "SUB", "CMP", "AND", "OR", "XOR", "SHL", "SHR",
          "LOAD_IND", "STORE_IND"}
JUMPS = {"JMP", "JZ", "JNZ", "JN", "JC", "JV", "CALL", "TRAP"}
MEM = {"LOAD", "STORE"}


def fmt(v):
    return str(v) if v < 10 else hex(v)


def load_words(path):
    if path.endswith(".hex"):
        with open(path, "r", encoding="utf-8") as f:
            return [int(line.strip(), 16) for line in f if line.strip()]
    with open(path, "rb") as f:
        data = f.read()
    return [w[0] for w in struct.iter_unpack("<H", data)]


def _fields_ok(op, w0, imm):
    """Un mot n'est décodé comme instruction que si ses champs sont
    canoniques (ce que l'assembleur émet) — sinon c'est une donnée."""
    rd = (w0 >> 8) & 0xF
    rs = (w0 >> 12) & 0xF
    cls = OPCLASS.get(op)
    if cls == "noarg":
        return rd == 0 and rs == 0 and imm == 0
    if cls == "reg1":
        return rs == 0 and imm == 0
    if cls == "regimm":
        return rs == 0
    if cls == "regreg":
        return imm == 0
    if cls == "jump":
        return rd == 0 and rs == 0
    if cls == "mem":
        return rs == 0
    return False


def disasm(words):
    # passe 1 : cibles de sauts -> labels
    targets = set()
    pc = 0
    while pc + 1 < len(words):
        w0 = words[pc]
        op = w0 & 0xFF
        if OPCLASS.get(op) == "jump" and _fields_ok(op, w0, words[pc + 1]):
            targets.add(words[pc + 1])
        pc += INSTR_SIZE
    labels = {t: f"L_{t:04x}" for t in sorted(targets)}

    lines = ["; désassemblé par tools/disasm.py — round-trip garanti"]
    pc = 0
    while pc < len(words):
        if pc in labels:
            lines.append(f"{labels[pc]}:")
        w0 = words[pc] & 0xFFFF
        op = w0 & 0xFF
        rd = (w0 >> 8) & 0xF
        rs = (w0 >> 12) & 0xF
        cls = OPCLASS.get(op)
        if cls is None or pc + 1 >= len(words) \
                or not _fields_ok(op, w0, words[pc + 1]):
            lines.append(f"    .word 0x{w0:04x}")
            pc += 1
            continue
        imm = words[pc + 1]
        name = NAME[op]
        if cls == "noarg":
            lines.append(f"    {name}")
        elif cls == "reg1":
            lines.append(f"    {name} R{rd}")
        elif cls == "regimm":
            lines.append(f"    {name} R{rd}, {fmt(imm)}")
        elif cls == "regreg":
            lines.append(f"    {name} R{rd}, R{rs}")
        elif cls == "jump":
            lines.append(f"    {name} {labels.get(imm, fmt(imm))}")
        else:
            lines.append(f"    {name} R{rd}, {fmt(imm)}")
        pc += INSTR_SIZE
    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 2:
        print("Usage: disasm.py <programme.hex|.bin> [-o sortie.r32]")
        sys.exit(1)
    src = sys.argv[1]
    out = None
    if "-o" in sys.argv:
        out = sys.argv[sys.argv.index("-o") + 1]
    words = load_words(src)
    text = disasm(words)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{out} : {len(words)} mots désassemblés")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

import os
import re
import struct

from isa import (
    OPCODES, INSTR_SIZE, NUM_REGISTERS, REG_NAMES,
    COMMENT_CHAR, WORD_MASK, OP_MOVRR,
)


class R32Assembler:
    """Assembleur R-32 v2.0 (2 passes).

    Passe 1   : collecte des labels (adresses de MOTS).
    Passe 1.5 : collecte des constantes .equ.
    Passe 2   : génération du code, 1 instruction = 2 mots :
                W0 = [opcode:8 | rd:4 | rs:4], W1 = imm16.

    Produit un .bin (mots 16 bits little-endian) et un .hex
    (un mot par ligne, format $readmemh pour Verilog/FPGA).
    """

    def __init__(self):
        self.labels = {}
        self.constants = {}

    @staticmethod
    def _clean(line):
        return line.split(COMMENT_CHAR, 1)[0].strip()

    def _resolve_reg(self, tok, line_no):
        tok = tok.strip().upper().replace(",", "")
        if tok in REG_NAMES:
            return REG_NAMES[tok]
        if tok.startswith("R"):
            try:
                idx = int(tok[1:])
            except ValueError:
                raise ValueError(f"Ligne {line_no} : registre invalide {tok!r}")
            if not (0 <= idx < NUM_REGISTERS):
                raise ValueError(f"Ligne {line_no} : R{idx} hors plage (0..{NUM_REGISTERS - 1})")
            return idx
        raise ValueError(f"Ligne {line_no} : registre attendu, reçu {tok!r}")

    CHAR_ESCAPES = {"n": 10, "r": 13, "t": 9, "0": 0, "\\": 92, "'": 39, '"': 34}

    def _parse_number(self, tok, line_no, max_value):
        tok = tok.strip().replace(",", "")
        if tok in self.constants:
            val = self.constants[tok]
        elif len(tok) >= 3 and tok[0] == "'" and tok[-1] == "'":
            # Littéral caractère : 'A', '\n', '\r', '\t', '\0', '\\', '\''
            inner = tok[1:-1]
            if len(inner) == 1:
                val = ord(inner)
            elif len(inner) == 2 and inner[0] == "\\" and inner[1] in self.CHAR_ESCAPES:
                val = self.CHAR_ESCAPES[inner[1]]
            else:
                raise ValueError(f"Ligne {line_no} : caractère invalide {tok!r}")
        else:
            try:
                val = int(tok, 16) if tok.lower().startswith("0x") else int(tok)
            except ValueError:
                raise ValueError(f"Ligne {line_no} : valeur invalide {tok!r}")

        if not (0 <= val <= max_value):
            raise ValueError(f"Ligne {line_no} : valeur {val} hors plage (0..{max_value})")
        return val

    STRING_RE = re.compile(r'^\.(ascii|string)\s+"(.*)"\s*$')

    def _string_words(self, line, line_no):
        """.ascii "text" -> mots du texte / .string "text" -> + terminateur NUL."""
        m = self.STRING_RE.match(line)
        if not m:
            raise ValueError(f'Ligne {line_no} : syntaxe .string "texte" attendue')
        kind, text = m.group(1), m.group(2)
        words = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\\" and i + 1 < len(text) and text[i + 1] in self.CHAR_ESCAPES:
                words.append(self.CHAR_ESCAPES[text[i + 1]])
                i += 2
            else:
                words.append(ord(ch))
                i += 1
        if kind == "string":
            words.append(0)
        return words

    def _parse_addr(self, tok, line_no, labels):
        tok = tok.strip().replace(",", "")
        if labels is not None and tok in labels:
            return labels[tok]
        return self._parse_number(tok, line_no, WORD_MASK)

    LABEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")

    @classmethod
    def _strip_label(cls, line):
        """Retire un éventuel label en début de ligne -> (label, reste)."""
        m = cls.LABEL_RE.match(line)
        if m:
            return m.group(1), m.group(2).strip()
        return None, line

    # ---------- Passe 1 : labels ----------
    def _collect_labels(self, lines):
        labels = {}
        pc = 0
        for line_no, raw in enumerate(lines, 1):
            line = self._clean(raw)
            if not line:
                continue

            # un ou plusieurs labels, seuls ou suivis de code
            while True:
                name, line = self._strip_label(line)
                if name is None:
                    break
                if name in labels:
                    raise ValueError(f"Ligne {line_no} : label déjà défini {name!r}")
                labels[name] = pc
            if not line:
                continue

            parts = line.split()
            head = parts[0].lower()

            if head in (".equ", ".org", ".align", ".word", ".byte",
                        ".ascii", ".string"):
                if head == ".org":
                    pc = self._parse_number(parts[1], line_no, WORD_MASK)
                elif head == ".align":
                    n = self._parse_number(parts[1], line_no, 15)
                    align = 1 << n
                    pc = (pc + align - 1) & ~(align - 1)
                elif head in (".word", ".byte"):
                    pc += len(parts) - 1
                elif head == ".equ":
                    pass  # ne consomme pas de mémoire
                else:  # .ascii / .string
                    pc += len(self._string_words(line, line_no))
                continue

            pc += INSTR_SIZE

        return labels

    # ---------- Passe 2 : génération ----------
    TOKEN_RE = re.compile(r"'(?:\\.|[^'])'|\S+")

    @classmethod
    def _tokenize(cls, line):
        """Découpe en tokens en préservant les littéraux 'x' (même ' ')."""
        return cls.TOKEN_RE.findall(line.replace(",", " "))

    def _emit(self, line, line_no, labels):
        parts = self._tokenize(line)
        head = parts[0].upper()

        if head not in OPCODES:
            raise ValueError(f"Ligne {line_no} : instruction inconnue {parts[0]!r}")

        op = OPCODES[head]
        args = parts[1:]
        rd, rs = 0, 0
        imm = 0

        if head in ("HALT", "RET", "NOP", "IRET"):
            if args:
                raise ValueError(f"Ligne {line_no} : {head} ne prend aucun argument")

        elif head in ("INC", "DEC", "PUSH", "POP"):
            if len(args) != 1:
                raise ValueError(f"Ligne {line_no} : {head} R_x")
            rd = self._resolve_reg(args[0], line_no)
            if head in ("INC", "DEC"):
                imm = 1  # l'ALU (ADD/SUB avec B=imm) en a besoin sur FPGA

        elif head in ("MOV", "MOVL"):
            if len(args) != 2:
                raise ValueError(f"Ligne {line_no} : {head} R_x, imm16|R_y|label")
            rd = self._resolve_reg(args[0], line_no)
            try:
                rs = self._resolve_reg(args[1], line_no)
            except ValueError:
                rs = 0
                imm = self._parse_addr(args[1], line_no, labels)
            else:
                # MOV Rd, Rs : copie registre -> registre
                op = OP_MOVRR

        elif head in ("ADD", "SUB", "CMP", "AND", "OR", "XOR", "SHL", "SHR",
                      "LOAD_IND", "STORE_IND"):
            if len(args) != 2:
                raise ValueError(f"Ligne {line_no} : {head} R_x, R_y")
            rd = self._resolve_reg(args[0], line_no)
            rs = self._resolve_reg(args[1], line_no)

        elif head == "CLR":
            # Pseudo-instruction : CLR Rd  ==  XOR Rd, Rd
            if len(args) != 1:
                raise ValueError(f"Ligne {line_no} : CLR R_x")
            rd = self._resolve_reg(args[0], line_no)
            rs = rd
            op = OPCODES["XOR"]

        elif head == "CMPI":
            if len(args) != 2:
                raise ValueError(f"Ligne {line_no} : CMPI R_x, imm16")
            rd = self._resolve_reg(args[0], line_no)
            imm = self._parse_number(args[1], line_no, WORD_MASK)

        elif head in ("JZ", "JNZ", "JN", "JC", "JV", "JMP", "CALL", "TRAP"):
            if len(args) != 1:
                raise ValueError(f"Ligne {line_no} : {head} adresse|label")
            imm = self._parse_addr(args[0], line_no, labels)

        elif head in ("LOAD", "STORE"):
            if len(args) != 2:
                raise ValueError(f"Ligne {line_no} : {head} R_x, addr16")
            rd = self._resolve_reg(args[0], line_no)
            imm = self._parse_addr(args[1], line_no, labels)

        w0 = op | (rd << 8) | (rs << 12)
        return [w0, imm]

    def assemble_lines(self, lines):
        # Passe 1 : labels
        self.labels = self._collect_labels(lines)

        # Passe 1.5 : constantes
        self.constants = {}
        for line_no, raw in enumerate(lines, 1):
            line = self._clean(raw)
            if not line:
                continue
            parts = line.replace(",", " ").split()
            if parts[0].lower() == ".equ":
                if len(parts) != 3:
                    raise ValueError(f"Ligne {line_no} : .equ NAME, valeur")
                name = parts[1]
                val = self._parse_number(parts[2], line_no, WORD_MASK)
                self.constants[name] = val

        # Passe 2 : génération
        buffer = {}
        pc = 0

        for line_no, raw in enumerate(lines, 1):
            line = self._clean(raw)
            if not line:
                continue
            _, line = self._strip_label(line)  # le label a déjà été compté en passe 1
            if not line:
                continue

            parts = self._tokenize(line)
            head = parts[0].lower()

            if head == ".equ":
                continue
            elif head == ".org":
                pc = self._parse_number(parts[1], line_no, WORD_MASK)
            elif head == ".align":
                n = self._parse_number(parts[1], line_no, 15)
                align = 1 << n
                pc = (pc + align - 1) & ~(align - 1)
            elif head == ".byte":
                raise ValueError(
                    f"Ligne {line_no} : .byte supprimé en v2.0 (mémoire 16 bits) — utilisez .word"
                )
            elif head in (".ascii", ".string"):
                for val in self._string_words(line, line_no):
                    buffer[pc] = val
                    pc += 1
            elif head == ".word":
                for a in parts[1:]:
                    val = self._parse_number(a, line_no, WORD_MASK)
                    buffer[pc] = val
                    pc += 1
            else:
                instr = self._emit(line, line_no, self.labels)
                for i, w in enumerate(instr):
                    buffer[pc + i] = w
                pc += INSTR_SIZE

        if not buffer:
            return []

        max_addr = max(buffer)
        out = [0] * (max_addr + 1)
        for addr, w in buffer.items():
            out[addr] = w & WORD_MASK
        return out

    def assemble_file(self, input_path, output_path):
        with open(input_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        bytecode = self.assemble_lines(lines)

        # .bin : mots 16 bits little-endian
        with open(output_path, "wb") as f:
            f.write(b"".join(struct.pack("<H", w) for w in bytecode))

        # .hex : un mot par ligne, format $readmemh (Verilog)
        hex_path = os.path.splitext(output_path)[0] + ".hex"
        with open(hex_path, "w", encoding="utf-8") as f:
            f.write("\n".join(f"{w:04x}" for w in bytecode))
            f.write("\n")

        return bytecode

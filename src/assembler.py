from isa import (
    OPCODES, INSTR_SIZE, NUM_REGISTERS, REG_NAMES,
    DIRECTIVES, COMMENT_CHAR,
)

class R32Assembler:
    """
    Assembleur 2 passes robuste.
    Passe 1 : Collecte des labels.
    Passe 2 : Génération du bytecode avec validation stricte.
    """

    def __init__(self):
        self.labels = {}
        self.constants = {}

    @staticmethod
    def _clean(line):
        # Enlève les commentaires et les espaces inutiles
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

    def _parse_number(self, tok, line_no, max_value):
        tok = tok.strip().replace(",", "")
        
        # --- FIX v1.1 : On vérifie d'abord si c'est un label de données ---
        if tok in self.labels:
            val = self.labels[tok]
        elif tok in self.constants:
            val = self.constants[tok]
        else:
            try:
                # Gère le décimal (42) et l'hexadécimal (0x2A)
                val = int(tok, 16) if tok.lower().startswith("0x") else int(tok)
            except ValueError:
                raise ValueError(f"Ligne {line_no} : valeur ou label invalide {tok!r}")
        
        if not (0 <= val <= max_value):
            raise ValueError(f"Ligne {line_no} : valeur {val} hors plage (0..{max_value})")
        return val

    def _parse_addr(self, tok, line_no, labels):
        tok = tok.strip().replace(",", "")
        if labels is not None and tok in labels:
            return labels[tok]
        return self._parse_number(tok, line_no, 0xFFFF)

    # ---------- Passe 1 : labels ----------
    def _collect_labels(self, lines):
        labels = {}
        pc = 0
        for line_no, raw in enumerate(lines, 1):
            line = self._clean(raw)
            if not line:
                continue

            if line.endswith(":"):
                name = line[:-1].strip()
                if not name:
                    raise ValueError(f"Ligne {line_no} : label vide")
                if name in labels:
                    raise ValueError(f"Ligne {line_no} : label déjà défini {name!r}")
                labels[name] = pc
                continue

            parts = line.split()
            head = parts[0].lower()

            if head in (".equ", ".org", ".align", ".byte", ".word"):
                if head == ".org":
                    pc = self._parse_number(parts[1], line_no, 0xFFFF)
                elif head == ".align":
                    n = self._parse_number(parts[1], line_no, 8)
                    align = 1 << n
                    pc = (pc + align - 1) & ~(align - 1)
                elif head in (".byte", ".word"):
                    size = 1 if head == ".byte" else 2
                    pc += size * (len(parts) - 1)
                continue

            pc += INSTR_SIZE

        return labels

    # ---------- Passe 2 : génération ----------
    def _emit(self, line, line_no, labels):
        # Remplace les virgules par des espaces pour faciliter le split
        parts = line.replace(",", " ").split()
        head = parts[0].upper()
        
        if head not in OPCODES:
            raise ValueError(f"Ligne {line_no} : instruction inconnue {parts[0]!r}")
        
        op = OPCODES[head]
        args = parts[1:]
        rd, rs, imm = 0, 0, 0

        if head in ("HALT", "RET", "NOP"):
            if args:
                raise ValueError(f"Ligne {line_no} : {head} ne prend aucun argument")

        elif head in ("PRINT", "READ", "PRINT_CHAR"):
            if len(args) != 1: raise ValueError(f"Ligne {line_no} : {head} R_x")
            rd = self._resolve_reg(args[0], line_no)

        elif head in ("INC", "DEC", "PUSH", "POP"):
            if len(args) != 1: raise ValueError(f"Ligne {line_no} : {head} R_x")
            rd = self._resolve_reg(args[0], line_no)

        elif head == "MOV":
            if len(args) != 2: raise ValueError(f"Ligne {line_no} : MOV R_x, imm8")
            rd = self._resolve_reg(args[0], line_no)
            imm = self._parse_number(args[1], line_no, 0xFF)

        # --- NOUVEAU v1.2 : MOVL (Move Long, 16 bits) ---
        elif head == "MOVL":
            if len(args) != 2: raise ValueError(f"Ligne {line_no} : MOVL R_x, adresse|label")
            rd = self._resolve_reg(args[0], line_no)
            addr = self._parse_addr(args[1], line_no, labels) # On accepte les labels !
            rs = addr & 0xFF         # Octet de poids faible
            imm = (addr >> 8) & 0xFF # Octet de poids fort
        # ------------------------------------------------

        elif head in ("ADD", "SUB", "CMP", "AND", "OR", "XOR", "SHL", "SHR", "LOAD_IND", "STORE_IND"):
            if len(args) != 2: raise ValueError(f"Ligne {line_no} : {head} R_x, R_y")
            rd = self._resolve_reg(args[0], line_no)
            rs = self._resolve_reg(args[1], line_no)

        elif head == "CMPI":
            if len(args) != 2: raise ValueError(f"Ligne {line_no} : CMPI R_x, imm8")
            rd = self._resolve_reg(args[0], line_no)
            imm = self._parse_number(args[1], line_no, 0xFF)

        elif head in ("JZ", "JNZ", "JN", "JMP", "CALL"):
            if len(args) != 1: raise ValueError(f"Ligne {line_no} : {head} adresse|label")
            addr = self._parse_addr(args[0], line_no, labels)
            rs = addr & 0xFF
            imm = (addr >> 8) & 0xFF

        elif head in ("LOAD", "STORE"):
            if len(args) != 2: raise ValueError(f"Ligne {line_no} : {head} R_x, addr8")
            rd = self._resolve_reg(args[0], line_no)
            imm = self._parse_number(args[1], line_no, 0xFF)

        return [op, rd, rs, imm]

    def assemble_lines(self, lines):
        # Passe 1 : Labels
        self.labels = self._collect_labels(lines)
        
        # Passe 1.5 : Constantes
        self.constants = {}
        for line_no, raw in enumerate(lines, 1):
            line = self._clean(raw)
            if not line: continue
            parts = line.replace(",", " ").split()
            if parts[0].lower() == ".equ":
                if len(parts) != 3: raise ValueError(f"Ligne {line_no} : .equ NAME, valeur")
                name = parts[1]
                val = self._parse_number(parts[2], line_no, 0xFFFF)
                self.constants[name] = val

        # Passe 2 : Génération
        buffer = {}
        pc = 0

        for line_no, raw in enumerate(lines, 1):
            line = self._clean(raw)
            if not line or line.endswith(":"):
                continue
                
            parts = line.replace(",", " ").split()
            head = parts[0].lower()

            if head == ".equ":
                continue
            elif head == ".org":
                pc = self._parse_number(parts[1], line_no, 0xFFFF)
            elif head == ".align":
                n = self._parse_number(parts[1], line_no, 8)
                align = 1 << n
                pc = (pc + align - 1) & ~(align - 1)
            elif head in (".byte", ".word"):
                size = 1 if head == ".byte" else 2
                maxv = 0xFF if size == 1 else 0xFFFF
                for a in parts[1:]:
                    val = self._parse_number(a, line_no, maxv)
                    if size == 1:
                        buffer[pc] = val & 0xFF
                        pc += 1
                    else:
                        buffer[pc] = val & 0xFF
                        buffer[pc + 1] = (val >> 8) & 0xFF
                        pc += 2
            else:
                instr = self._emit(line, line_no, self.labels)
                for i, b in enumerate(instr):
                    buffer[pc + i] = b
                pc += INSTR_SIZE

        if not buffer:
            return []

        max_addr = max(buffer)
        out = bytearray(max_addr + 1)
        for addr, b in buffer.items():
            out[addr] = b & 0xFF
        return list(out)

    def assemble_file(self, input_path, output_path):
        with open(input_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        bytecode = self.assemble_lines(lines)
        with open(output_path, "wb") as f:
            f.write(bytes(bytecode))
        return bytecode
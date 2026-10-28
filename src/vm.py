from memory import MemoryManager
from iobus import IOBus
from isa import (
    NUM_REGISTERS, INSTR_SIZE, WORD_MASK,
    REG_ZERO, REG_SP, REG_LR,
    FLAG_Z, FLAG_N, FLAG_C, FLAG_V,
    # opcodes
    OP_HALT, OP_MOV, OP_ADD, OP_SUB, OP_CMP, OP_CMPI,
    OP_AND, OP_OR, OP_XOR, OP_SHL, OP_SHR, OP_INC, OP_DEC,
    OP_LOAD, OP_STORE, OP_LOAD_IND, OP_STORE_IND,
    OP_JMP, OP_JZ, OP_JNZ, OP_JN, OP_JC, OP_JV,
    OP_CALL, OP_RET, OP_PUSH, OP_POP, OP_NOP, OP_MOVRR,
    OP_IRET, OP_TRAP,
)


class R32VM:
    """VM R-32 v2.0 — 16 bits.

    Instruction = 2 mots :
      W0 = [opcode:8 | rd:4 | rs:4]
      W1 = imm16
    Registres 16 bits ; mémoire 64 Kmots ; I/O via UART MMIO.
    Sémantique adaptée à une implémentation FPGA monocycle.
    """

    def __init__(self, memory_size=0x10000):
        self.iobus = IOBus()
        self.uart = self.iobus.uart  # compatibilité
        self.registers = [0] * NUM_REGISTERS
        self.mem = MemoryManager(size=memory_size, mmio=self.iobus)
        self.pc = 0
        self.flags = {FLAG_Z: 0, FLAG_N: 0, FLAG_C: 0, FLAG_V: 0}
        self.halted = False
        self.in_irq = False   # v3.0 : pas de nesting d'IRQ
        self.registers[REG_SP] = self.mem.STACK_TOP
        self.iobus.attach_mem(self.mem)   # v3.1 : la VGA lit la VRAM partagée

    def _flags_word(self):
        return (self.flags[FLAG_Z] | self.flags[FLAG_N] << 1
                | self.flags[FLAG_C] << 2 | self.flags[FLAG_V] << 3)

    def _restore_flags(self, word):
        self.flags[FLAG_Z] = word & 1
        self.flags[FLAG_N] = (word >> 1) & 1
        self.flags[FLAG_C] = (word >> 2) & 1
        self.flags[FLAG_V] = (word >> 3) & 1

    def _check_reg(self, idx, ctx=""):
        if not (0 <= idx < NUM_REGISTERS):
            raise ValueError(f"{ctx} : registre R{idx} hors plage (0..{NUM_REGISTERS-1})")

    def _set_flags(self, result, carry=0, overflow=0):
        """Met à jour Z/N/C/V. `result` est le résultat mathématique brut."""
        r = result & WORD_MASK
        self.flags[FLAG_Z] = 1 if r == 0 else 0
        self.flags[FLAG_N] = 1 if (r & 0x8000) else 0
        self.flags[FLAG_C] = 1 if carry else 0
        self.flags[FLAG_V] = 1 if overflow else 0

    @staticmethod
    def _overflow_add(a, b, r):
        """Overflow signé 16 bits pour a + b = r."""
        sa, sb, sr = (a >> 15) & 1, (b >> 15) & 1, (r >> 15) & 1
        return int(sa == sb and sa != sr)

    @staticmethod
    def _overflow_sub(a, b, r):
        """Overflow signé 16 bits pour a - b = r."""
        sa, sb, sr = (a >> 15) & 1, (b >> 15) & 1, (r >> 15) & 1
        return int(sa != sb and sa != sr)

    def _write_reg(self, idx, value):
        if idx != REG_ZERO:
            self.registers[idx] = value & WORD_MASK

    def _push(self, value):
        """Empile un mot (la pile grandit vers le bas)."""
        sp = (self.registers[REG_SP] - 1) & WORD_MASK
        self.mem.write(sp, value)
        self.registers[REG_SP] = sp

    def _pop(self):
        """Dépile un mot."""
        sp = self.registers[REG_SP]
        value = self.mem.read(sp)
        self.registers[REG_SP] = (sp + 1) & WORD_MASK
        return value

    def load_program(self, bytecode, start_address=0):
        self.mem.load_program(bytecode, start_address)
        self.pc = start_address
        self.halted = False

    def step(self):
        """Exécute une seule instruction (ou sert une IRQ en attente)."""
        if self.halted:
            return False

        # --- v3.0/3.1 : timer, périphériques, servitude des IRQ ---
        self.iobus.timer.tick()
        self.iobus.poll()
        if not self.in_irq and self.iobus.take_pending():
            self._push(self.pc)
            self._push(self._flags_word())
            self.pc = self.iobus.timer.vector
            self.in_irq = True
            return True

        # 1. FETCH (2 mots)
        w0 = self.mem.read(self.pc)
        imm = self.mem.read(self.pc + 1)
        opcode = w0 & 0xFF
        rd = (w0 >> 8) & 0xF
        rs = (w0 >> 12) & 0xF

        next_pc = (self.pc + INSTR_SIZE) & WORD_MASK

        # Sécurité : R0 est toujours 0
        self.registers[REG_ZERO] = 0

        # 2. DECODE & EXECUTE
        if opcode == OP_HALT:
            self.halted = True
            return False

        elif opcode == OP_NOP:
            pass

        elif opcode == OP_MOV:
            self._check_reg(rd, "MOV")
            self._write_reg(rd, imm)

        elif opcode == OP_MOVRR:
            self._check_reg(rd, "MOV"); self._check_reg(rs, "MOV")
            self._write_reg(rd, self.registers[rs])

        elif opcode == OP_ADD:
            self._check_reg(rd, "ADD"); self._check_reg(rs, "ADD")
            a, b = self.registers[rd], self.registers[rs]
            res = a + b
            self._write_reg(rd, res)
            self._set_flags(res, carry=res > WORD_MASK,
                            overflow=self._overflow_add(a, b, res & WORD_MASK))

        elif opcode == OP_SUB:
            self._check_reg(rd, "SUB"); self._check_reg(rs, "SUB")
            a, b = self.registers[rd], self.registers[rs]
            res = a - b
            self._write_reg(rd, res)
            self._set_flags(res, carry=res < 0,
                            overflow=self._overflow_sub(a, b, res & WORD_MASK))

        elif opcode == OP_CMP:
            self._check_reg(rd, "CMP"); self._check_reg(rs, "CMP")
            a, b = self.registers[rd], self.registers[rs]
            res = a - b
            self._set_flags(res, carry=res < 0,
                            overflow=self._overflow_sub(a, b, res & WORD_MASK))

        elif opcode == OP_CMPI:
            self._check_reg(rd, "CMPI")
            a = self.registers[rd]
            res = a - imm
            self._set_flags(res, carry=res < 0,
                            overflow=self._overflow_sub(a, imm, res & WORD_MASK))

        elif opcode == OP_AND:
            self._check_reg(rd, "AND"); self._check_reg(rs, "AND")
            res = self.registers[rd] & self.registers[rs]
            self._write_reg(rd, res)
            self._set_flags(res)

        elif opcode == OP_OR:
            self._check_reg(rd, "OR"); self._check_reg(rs, "OR")
            res = self.registers[rd] | self.registers[rs]
            self._write_reg(rd, res)
            self._set_flags(res)

        elif opcode == OP_XOR:
            self._check_reg(rd, "XOR"); self._check_reg(rs, "XOR")
            res = self.registers[rd] ^ self.registers[rs]
            self._write_reg(rd, res)
            self._set_flags(res)

        elif opcode == OP_SHL:
            self._check_reg(rd, "SHL"); self._check_reg(rs, "SHL")
            a = self.registers[rd]
            res = a << self.registers[rs]
            self._write_reg(rd, res)
            self._set_flags(res, carry=(res >> 16) != 0)

        elif opcode == OP_SHR:
            self._check_reg(rd, "SHR"); self._check_reg(rs, "SHR")
            res = self.registers[rd] >> self.registers[rs]
            self._write_reg(rd, res)
            self._set_flags(res)

        elif opcode == OP_INC:
            self._check_reg(rd, "INC")
            a = self.registers[rd]
            res = a + 1
            self._write_reg(rd, res)
            self._set_flags(res, carry=res > WORD_MASK,
                            overflow=self._overflow_add(a, 1, res & WORD_MASK))

        elif opcode == OP_DEC:
            self._check_reg(rd, "DEC")
            a = self.registers[rd]
            res = a - 1
            self._write_reg(rd, res)
            self._set_flags(res, carry=res < 0,
                            overflow=self._overflow_sub(a, 1, res & WORD_MASK))

        elif opcode == OP_JMP:
            next_pc = imm

        elif opcode == OP_JZ:
            if self.flags[FLAG_Z] == 1:
                next_pc = imm

        elif opcode == OP_JNZ:
            if self.flags[FLAG_Z] == 0:
                next_pc = imm

        elif opcode == OP_JN:
            if self.flags[FLAG_N] == 1:
                next_pc = imm

        elif opcode == OP_JC:
            if self.flags[FLAG_C] == 1:
                next_pc = imm

        elif opcode == OP_JV:
            if self.flags[FLAG_V] == 1:
                next_pc = imm

        elif opcode == OP_CALL:
            self.registers[REG_LR] = next_pc  # adresse de retour
            next_pc = imm

        elif opcode == OP_RET:
            next_pc = self.registers[REG_LR]

        elif opcode == OP_LOAD:
            self._check_reg(rd, "LOAD")
            self._write_reg(rd, self.mem.read(imm))

        elif opcode == OP_STORE:
            self._check_reg(rd, "STORE")
            self.mem.write(imm, self.registers[rd])

        elif opcode == OP_LOAD_IND:
            self._check_reg(rd, "LOAD_IND"); self._check_reg(rs, "LOAD_IND")
            value = self.mem.read(self.registers[rs])
            self._write_reg(rd, value)
            self._set_flags(value)

        elif opcode == OP_STORE_IND:
            self._check_reg(rd, "STORE_IND"); self._check_reg(rs, "STORE_IND")
            self.mem.write(self.registers[rs], self.registers[rd])

        elif opcode == OP_PUSH:
            self._check_reg(rd, "PUSH")
            self._push(self.registers[rd])

        elif opcode == OP_POP:
            self._check_reg(rd, "POP")
            if rd != REG_ZERO:
                self.registers[rd] = self._pop()

        elif opcode == OP_IRET:
            flags_word = self._pop()
            next_pc = self._pop()
            self._restore_flags(flags_word)
            self.in_irq = False

        elif opcode == OP_TRAP:
            self._push(next_pc)
            self._push(self._flags_word())
            next_pc = imm

        else:
            raise ValueError(f"Opcode inconnu 0x{opcode:02X} à l'adresse {hex(self.pc)}")

        self.pc = next_pc
        return True

    def run(self, max_steps=1_000_000):
        """Lance le programme jusqu'à HALT."""
        steps = 0
        while not self.halted:
            if steps >= max_steps:
                raise RuntimeError(f"Boucle infinie suspectée ({max_steps} étapes), PC = {hex(self.pc)}")
            self.step()
            steps += 1
        return steps

from memory import MemoryManager
from isa import (
    NUM_REGISTERS, INSTR_SIZE, REG_ZERO, REG_SP, REG_LR,
    FLAG_Z, FLAG_N, FLAG_C, FLAG_V,
    # opcodes
    OP_HALT, OP_PRINT, OP_MOV, OP_ADD, OP_SUB, OP_CMP,
    OP_JZ, OP_JMP, OP_LOAD, OP_STORE, OP_NOP,
    OP_AND, OP_OR, OP_XOR, OP_SHL, OP_SHR,
    OP_JNZ, OP_JN, OP_PUSH, OP_POP, OP_CALL, OP_RET,
    OP_INC, OP_DEC,
)


class R32VM:
    def __init__(self, memory_size=65536):
        self.registers = [0] * NUM_REGISTERS
        self.mem = MemoryManager(size=memory_size)
        self.pc = 0
        self.flags = {FLAG_Z: 0, FLAG_N: 0, FLAG_C: 0, FLAG_V: 0}
        self.halted = False
        # Initialisation du Stack Pointer (SP) tout en haut de la pile
        self.registers[REG_SP] = self.mem.STACK_TOP

    def _check_reg(self, idx, ctx=""):
        """Vérifie que le registre demandé existe bien (entre 0 et 15)."""
        if not (0 <= idx < NUM_REGISTERS):
            raise ValueError(f"{ctx} : registre R{idx} hors plage (0..{NUM_REGISTERS-1})")

    def _set_flags(self, result):
        """Met à jour les drapeaux (Flags) après un calcul."""
        self.flags[FLAG_Z] = 1 if result == 0 else 0
        self.flags[FLAG_N] = 1 if result < 0 else 0
        # Flag Carry (débordement non signé)
        self.flags[FLAG_C] = 1 if (result < 0 or result > 0xFF) else 0
        # Flag Overflow (réservé pour plus tard)
        self.flags[FLAG_V] = 0  

    def _push(self, value):
        """Empile une valeur (la pile grandit vers le bas)."""
        sp = self.registers[REG_SP] - 1
        self.mem.write(sp, value & 0xFF)
        self.registers[REG_SP] = sp

    def _pop(self):
        """Dépile une valeur."""
        sp = self.registers[REG_SP]
        value = self.mem.read(sp)
        self.registers[REG_SP] = sp + 1
        return value

    def load_program(self, bytecode, start_address=0):
        self.mem.load_program(bytecode, start_address)
        self.pc = start_address
        self.halted = False

    def step(self):
        """Exécute une seule instruction."""
        if self.halted:
            return False

        # 1. FETCH : On lit les 4 octets de l'instruction
        opcode = self.mem.read(self.pc)
        rd = self.mem.read(self.pc + 1)
        rs = self.mem.read(self.pc + 2)
        imm = self.mem.read(self.pc + 3)
        
        # On calcule l'adresse de la PROCHAINE instruction (par défaut)
        next_pc = self.pc + INSTR_SIZE

        # Sécurité : R0 est toujours 0
        self.registers[REG_ZERO] = 0

        # 2. DECODE & EXECUTE
        if opcode == OP_HALT:
            self.halted = True
            return False

        elif opcode == OP_NOP:
            pass  # Ne fait rien

        elif opcode == OP_PRINT:
            self._check_reg(rd, "PRINT")
            print(f"R{rd} = {self.registers[rd]}")

        elif opcode == OP_MOV:
            self._check_reg(rd, "MOV")
            if rd != REG_ZERO:
                self.registers[rd] = imm

        elif opcode == OP_ADD:
            self._check_reg(rd, "ADD"); self._check_reg(rs, "ADD")
            res = self.registers[rd] + self.registers[rs]
            if rd != REG_ZERO:
                self.registers[rd] = res
            self._set_flags(res)

        elif opcode == OP_SUB:
            self._check_reg(rd, "SUB"); self._check_reg(rs, "SUB")
            res = self.registers[rd] - self.registers[rs]
            if rd != REG_ZERO:
                self.registers[rd] = res
            self._set_flags(res)

        elif opcode == OP_CMP:
            self._check_reg(rd, "CMP"); self._check_reg(rs, "CMP")
            # CMP ne modifie pas le registre, il met juste à jour les flags
            self._set_flags(self.registers[rd] - self.registers[rs])

        elif opcode == OP_AND:
            self._check_reg(rd, "AND"); self._check_reg(rs, "AND")
            res = self.registers[rd] & self.registers[rs]
            if rd != REG_ZERO: self.registers[rd] = res
            self._set_flags(res)

        elif opcode == OP_OR:
            self._check_reg(rd, "OR"); self._check_reg(rs, "OR")
            res = self.registers[rd] | self.registers[rs]
            if rd != REG_ZERO: self.registers[rd] = res
            self._set_flags(res)

        elif opcode == OP_XOR:
            self._check_reg(rd, "XOR"); self._check_reg(rs, "XOR")
            res = self.registers[rd] ^ self.registers[rs]
            if rd != REG_ZERO: self.registers[rd] = res
            self._set_flags(res)

        elif opcode == OP_SHL:
            self._check_reg(rd, "SHL"); self._check_reg(rs, "SHL")
            res = self.registers[rd] << self.registers[rs]
            if rd != REG_ZERO: self.registers[rd] = res
            self._set_flags(res)

        elif opcode == OP_SHR:
            self._check_reg(rd, "SHR"); self._check_reg(rs, "SHR")
            res = self.registers[rd] >> self.registers[rs]
            if rd != REG_ZERO: self.registers[rd] = res
            self._set_flags(res)

        elif opcode == OP_INC:
            self._check_reg(rd, "INC")
            res = self.registers[rd] + 1
            if rd != REG_ZERO: self.registers[rd] = res
            self._set_flags(res)

        elif opcode == OP_DEC:
            self._check_reg(rd, "DEC")
            res = self.registers[rd] - 1
            if rd != REG_ZERO: self.registers[rd] = res
            self._set_flags(res)

        elif opcode == OP_JZ:
            target = rs | (imm << 8)
            if self.flags[FLAG_Z] == 1:
                next_pc = target

        elif opcode == OP_JNZ:
            target = rs | (imm << 8)
            if self.flags[FLAG_Z] == 0:
                next_pc = target

        elif opcode == OP_JN:
            target = rs | (imm << 8)
            if self.flags[FLAG_N] == 1:
                next_pc = target

        elif opcode == OP_JMP:
            next_pc = rs | (imm << 8)

        elif opcode == OP_CALL:
            target = rs | (imm << 8)
            self.registers[REG_LR] = next_pc  # Sauvegarde l'adresse de retour
            next_pc = target

        elif opcode == OP_RET:
            next_pc = self.registers[REG_LR]

        elif opcode == OP_LOAD:
            self._check_reg(rd, "LOAD")
            self.registers[rd] = self.mem.read(imm)

        elif opcode == OP_STORE:
            self._check_reg(rd, "STORE")
            self.mem.write(imm, self.registers[rd] & 0xFF)

        elif opcode == OP_PUSH:
            self._check_reg(rd, "PUSH")
            self._push(self.registers[rd])

        elif opcode == OP_POP:
            self._check_reg(rd, "POP")
            if rd != REG_ZERO:
                self.registers[rd] = self._pop()

        else:
            raise ValueError(f"Opcode inconnu 0x{opcode:02X} à l'adresse {hex(self.pc)}")

        # 3. UPDATE PC (Mise à jour du compteur de programme)
        self.pc = next_pc
        return True

    def run(self, max_steps=100_000):
        """Lance le programme jusqu'à HALT."""
        steps = 0
        while not self.halted:
            if steps >= max_steps:
                raise RuntimeError(f"Boucle infinie suspectée ({max_steps} étapes), PC = {hex(self.pc)}")
            self.step()
            steps += 1
        return steps
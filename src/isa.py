"""
ISA R-32 v2.0 — 16 bits, cible FPGA.

RUPTURE de compatibilité avec v1.1 (voir CHANGELOG.md) :
- Mémoire organisée en mots de 16 bits (64 Kmots).
- Instruction = 2 mots : W0 = [opcode:8 | rd:4 | rs:4], W1 = imm16.
- PRINT / READ / PRINT_CHAR remplacés par un UART en MMIO.
- Flags C et V calculés pour de vrai ; sauts JC/JV ajoutés.
"""

ISA_VERSION = "3.0"
NUM_REGISTERS = 16
WORD_MASK = 0xFFFF

# --- DÉFINITION DES REGISTRES (16 bits) ---
REG_ZERO = 0
REG_RA   = 1
REG_A0   = 2    # R2  : argument 2
REG_A1   = 3    # R3  : argument 3
REG_T0   = 4    # R4  : temporaire
REG_T1   = 5    # R5  : temporaire
REG_T2   = 6    # R6  : temporaire
REG_S0   = 7    # R7  : sauvé (callee-saved)
REG_S1   = 8    # R8  : sauvé
REG_S2   = 9    # R9  : sauvé
REG_S3   = 10   # R10 : sauvé
REG_S4   = 11   # R11 : sauvé
REG_FP   = 12   # R12 : frame pointer
REG_SP   = 13   # R13 : stack pointer
REG_LR   = 14   # R14 : link register (CALL/RET)
REG_GP   = 15   # R15 : global pointer

REG_NAMES = {
    "ZERO": REG_ZERO, "RA": REG_RA, "A0": REG_A0, "A1": REG_A1,
    "T0": REG_T0, "T1": REG_T1, "T2": REG_T2,
    "S0": REG_S0, "S1": REG_S1, "S2": REG_S2, "S3": REG_S3, "S4": REG_S4,
    "FP": REG_FP, "SP": REG_SP, "LR": REG_LR, "GP": REG_GP,
}

# --- CARTE MÉMOIRE / MMIO ---
# 0x0000 - 0xEFFF : RAM (61 Kmots)
# 0xF000 - 0xFFFF : périfériques MMIO (4 Kmots)
MMIO_BASE   = 0xF000
UART_DATA   = 0xF000  # W : émet le caractère (8 bits) / R : caractère reçu (0 si aucun)
UART_STATUS = 0xF001  # R : bit0 = caractère disponible, bit1 = TX libre (toujours 1)
DEBUG_DEC   = 0xF002  # W : affiche la valeur en décimal (périphérique de débogage)

# --- v3.0 : timer + interruptions ---
TIMER_COUNT  = 0xF030  # R : compteur (s'incrémente à chaque cycle/instruction)
TIMER_PERIOD = 0xF031  # W : période d'IRQ (1..65535 active, 0 désactive)
TIMER_VECTOR = 0xF032  # W : adresse du handler IRQ (adresse de mot)
# Mot d'état sauvegardé sur IRQ/TRAP : bit0=Z, bit1=N, bit2=C, bit3=V

# --- v3.1 : périphériques ---
VGA_VRAM    = 0x8000  # RAM partagée : 80x25 caractères (2000 mots, 0x8000-0x87CF)
VGA_CURSX   = 0xF040  # W : curseur X (0..79)
VGA_CURSY   = 0xF041  # W : curseur Y (0..24)
KBD_DATA    = 0xF050  # R : scancode PS/2 set 1 (0 si vide)
KBD_STATUS  = 0xF051  # R : bit0 = scancode disponible
MOUSE_DATA  = 0xF060  # R : octet de paquet souris (3 octets/paquet)
MOUSE_STATUS = 0xF061  # R : bit0 = octet disponible

# --- OPCODES v2.0 ---
OP_HALT      = 0x00
OP_MOV       = 0x01   # Rd = imm16
OP_ADD       = 0x02
OP_SUB       = 0x03
OP_CMP       = 0x04   # flags = Rd - Rs
OP_CMPI      = 0x05   # flags = Rd - imm16
OP_AND       = 0x06
OP_OR        = 0x07
OP_XOR       = 0x08
OP_SHL       = 0x09
OP_SHR       = 0x0A
OP_INC       = 0x0B
OP_DEC       = 0x0C
OP_LOAD      = 0x0D   # Rd = mem[imm16]
OP_STORE     = 0x0E   # mem[imm16] = Rd
OP_LOAD_IND  = 0x0F   # Rd = mem[Rs]
OP_STORE_IND = 0x10   # mem[Rs] = Rd
OP_JMP       = 0x11
OP_JZ        = 0x12
OP_JNZ       = 0x13
OP_JN        = 0x14   # saute si N (résultat < 0, signé)
OP_JC        = 0x15   # saute si retenue
OP_JV        = 0x16   # saute si overflow signé
OP_CALL      = 0x17   # LR = PC + 2 ; PC = imm16
OP_RET       = 0x18   # PC = LR
OP_PUSH      = 0x19
OP_POP       = 0x1A
OP_NOP       = 0x1B
OP_MOVRR     = 0x1C   # Rd = Rs (forme registre->registre de MOV)
OP_IRET      = 0x1D   # v3.0 : flags <- pop() ; PC <- pop() (retour d'interruption)
OP_TRAP      = 0x1E   # v3.0 : push PC ; push flags ; PC = imm16 (syscall/logicielle)

DIRECTIVES = (".org", ".word", ".equ", ".align", ".ascii", ".string")

OPCODES = {
    "HALT":  OP_HALT,  "MOV":   OP_MOV,   "ADD":   OP_ADD,
    "SUB":   OP_SUB,   "CMP":   OP_CMP,   "CMPI":  OP_CMPI,
    "AND":   OP_AND,   "OR":    OP_OR,    "XOR":   OP_XOR,
    "SHL":   OP_SHL,   "SHR":   OP_SHR,   "INC":   OP_INC,
    "DEC":   OP_DEC,   "LOAD":  OP_LOAD,  "STORE": OP_STORE,
    "LOAD_IND":  OP_LOAD_IND,  "STORE_IND": OP_STORE_IND,
    "JMP":   OP_JMP,   "JZ":    OP_JZ,    "JNZ":   OP_JNZ,
    "JN":    OP_JN,    "JC":    OP_JC,    "JV":    OP_JV,
    "CALL":  OP_CALL,  "RET":   OP_RET,   "PUSH":  OP_PUSH,
    "POP":   OP_POP,   "NOP":   OP_NOP,
    "IRET":  OP_IRET,  "TRAP":  OP_TRAP,
    # Alias historique v1.1 (assemble comme MOV)
    "MOVL":  OP_MOV,
}

INSTR_SIZE = 2  # mots de 16 bits par instruction

FLAG_Z = "Z"  # zero
FLAG_N = "N"  # negative (signe)
FLAG_C = "C"  # carry (retenue)
FLAG_V = "V"  # overflow signé

FLAG_NAMES = (FLAG_Z, FLAG_N, FLAG_C, FLAG_V)

COMMENT_CHAR = ";"

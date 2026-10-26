"""
ISA R-32 v1.2 — FIGÉE.

Toute évolution doit incrémenter la version (v1.3, v2.0...)
et documenter la compatibilité dans un CHANGELOG.

NOUVEAUTÉ v1.2 :
- Ajout de MOVL (Move Immediate Long) pour charger des adresses 16 bits (0x0000 à 0xFFFF) dans un registre.
  Format : [opcode][rd][0][imm8] pour la partie haute, ou plus simple : on utilise une seule instruction
  qui lit imm16 dans les 2 octets suivants. Ici, on va ruser : MOVL Rd, imm16.
"""

ISA_VERSION = "1.2"
NUM_REGISTERS = 16

# --- DÉFINITION DES REGISTRES ---
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
REG_LR   = 14   
REG_GP   = 15   

REG_NAMES = {
    "ZERO": REG_ZERO, "RA": REG_RA, "A0": REG_A0, "A1": REG_A1,
    "T0": REG_T0, "T1": REG_T1, "T2": REG_T2,
    "S0": REG_S0, "S1": REG_S1, "S2": REG_S2, "S3": REG_S3, "S4": REG_S4,
    "FP": REG_FP, "SP": REG_SP, "LR": REG_LR, "GP": REG_GP,
}

# --- OPCODES ---
OP_HALT  = 0x00
OP_PRINT = 0x01
OP_MOV   = 0x02
OP_ADD   = 0x03
OP_SUB   = 0x04
OP_CMP   = 0x05
OP_JZ    = 0x06
OP_JMP   = 0x07
OP_LOAD  = 0x08
OP_STORE = 0x09
OP_NOP   = 0x0A
OP_AND   = 0x0B
OP_OR    = 0x0C
OP_XOR   = 0x0D
OP_SHL   = 0x0E
OP_SHR   = 0x0F
OP_JNZ   = 0x10
OP_JN    = 0x11
OP_PUSH  = 0x12
OP_POP   = 0x13
OP_CALL  = 0x14
OP_RET   = 0x15
OP_INC   = 0x16
OP_DEC   = 0x17

# --- NOUVEAUX OPCODES v1.1 ---
OP_READ       = 0x18
OP_PRINT_CHAR = 0x19
OP_LOAD_IND   = 0x1A
OP_STORE_IND  = 0x1B
OP_CMPI       = 0x1C

# --- NOUVEAUX OPCODES v1.2 ---
OP_MOVL       = 0x1D   # Charge une valeur immédiate 16 bits dans Rd
# -----------------------------

OPCODES = {
    "HALT":  OP_HALT,  "PRINT": OP_PRINT, "MOV":   OP_MOV,
    "ADD":   OP_ADD,   "SUB":   OP_SUB,   "CMP":   OP_CMP,
    "JZ":    OP_JZ,    "JMP":   OP_JMP,   "LOAD":  OP_LOAD,
    "STORE": OP_STORE, "NOP":   OP_NOP,   "AND":   OP_AND,
    "OR":    OP_OR,    "XOR":   OP_XOR,   "SHL":   OP_SHL,
    "SHR":   OP_SHR,   "JNZ":   OP_JNZ,   "JN":    OP_JN,
    "PUSH":  OP_PUSH,  "POP":   OP_POP,   "CALL":  OP_CALL,
    "RET":   OP_RET,   "INC":   OP_INC,   "DEC":   OP_DEC,
    
    # --- v1.1 ---
    "READ":       OP_READ,
    "PRINT_CHAR": OP_PRINT_CHAR,
    "LOAD_IND":   OP_LOAD_IND,
    "STORE_IND":  OP_STORE_IND,
    "CMPI":       OP_CMPI,
    
    # --- v1.2 ---
    "MOVL":       OP_MOVL,
}

INSTR_SIZE = 4
FLAG_Z = "Z"  # zero
FLAG_N = "N"  # negative
FLAG_C = "C"  # carry
FLAG_V = "V"  

FLAG_NAMES = (FLAG_Z, FLAG_N, FLAG_C, FLAG_V)

DIRECTIVES = (".org", ".byte", ".word", ".equ", ".align")

COMMENT_CHAR = ";"
# Architecture R-32 (v2.1)

## Vue d'ensemble

CPU 16 bits, RISC-like, pensé pour une implémentation FPGA monocycle
(une instruction par coup d'horloge). Recommandation matérielle :
architecture **Harvard** (mémoire programme 32 bits / mémoire données 16 bits).

## Registres (16 × 16 bits)

| Reg | Nom  | Usage                              |
|-----|------|------------------------------------|
| R0  | ZERO | toujours 0 (écritures ignorées)    |
| R1  | RA   | valeur de retour                   |
| R2  | A0   | argument 1                         |
| R3  | A1   | argument 2                         |
| R4-R6 | T0-T2 | temporaires (caller-saved)      |
| R7-R11 | S0-S4 | sauvés (callee-saved)           |
| R12 | FP   | frame pointer                      |
| R13 | SP   | stack pointer (pile vers le bas)   |
| R14 | LR   | link register (CALL/RET)           |
| R15 | GP   | global pointer                     |

## Format d'instruction (32 bits = 2 mots)

```
W0 = [ opcode:8 | rd:4 | rs:4 ]
W1 = imm16
```

Le PC s'incrémente de 2 mots par instruction. Toutes les instructions
tiennent dans le même format : décodage purement combinatoire.

## Instructions (opcodes v2.1)

| Op | Opcode | Description                        |
|----|--------|------------------------------------|
| 0x00 | HALT      | arrête le processeur            |
| 0x01 | MOV       | Rd = imm16 (alias historique MOVL) |
| 0x1C | MOVRR     | Rd = Rs (forme reg→reg de MOV)  |
| 0x02 | ADD       | Rd = Rd + Rs                    |
| 0x03 | SUB       | Rd = Rd - Rs                    |
| 0x04 | CMP       | flags = Rd - Rs                 |
| 0x05 | CMPI      | flags = Rd - imm16              |
| 0x06 | AND       | Rd = Rd & Rs                    |
| 0x07 | OR        | Rd = Rd \| Rs                   |
| 0x08 | XOR       | Rd = Rd ^ Rs                    |
| 0x09 | SHL       | Rd = Rd << Rs                   |
| 0x0A | SHR       | Rd = Rd >> Rs                   |
| 0x0B | INC       | Rd = Rd + 1                     |
| 0x0C | DEC       | Rd = Rd - 1                     |
| 0x0D | LOAD      | Rd = mem[imm16]                 |
| 0x0E | STORE     | mem[imm16] = Rd                 |
| 0x0F | LOAD_IND  | Rd = mem[Rs]                    |
| 0x10 | STORE_IND | mem[Rs] = Rd                    |
| 0x11 | JMP       | PC = imm16                      |
| 0x12 | JZ        | PC = imm16 si Z                 |
| 0x13 | JNZ       | PC = imm16 si !Z                |
| 0x14 | JN        | PC = imm16 si N (signé)         |
| 0x15 | JC        | PC = imm16 si C (retenue)       |
| 0x16 | JV        | PC = imm16 si V (overflow)      |
| 0x17 | CALL      | LR = PC + 2 ; PC = imm16        |
| 0x18 | RET       | PC = LR                         |
| 0x19 | PUSH      | mem[--SP] = Rd                  |
| 0x1A | POP       | Rd = mem[SP++]                  |
| 0x1B | NOP       | rien                            |

Pseudo-instruction assembleur : `CLR Rd` → `XOR Rd, Rd`.

## Flags

| Flag | Signification                                        |
|------|------------------------------------------------------|
| Z    | résultat 0 (mod 2^16)                                 |
| N    | bit 15 du résultat (signe, arithmétique signée)       |
| C    | retenue (ADD : sortie 16 bits / SUB : emprunt)        |
| V    | overflow en complément à 2 (ADD/SUB)                  |

## Mémoire

- 64 Kmots de 16 bits, adressage au mot.
- `0x0000-0xEFFF` : RAM. Le programme doit tenir dans cette zone.
- `0xF000-0xFFFF` : MMIO (voir README pour la carte).
- Pile : SP initialisé à `0xEFFF`, croît vers les adresses basses.

## Flow d'exécution (monocycle)

1. **Fetch** : W0 ← mem[PC], W1 ← mem[PC+1]
2. **Decode** : opcode = W0[7:0], rd = W0[11:8], rs = W0[15:12], imm = W1
3. **Execute** : ALU / accès mémoire / branchement
4. **PC** : PC+2, ou cible du saut, ou LR (RET), ou arrêt (HALT)

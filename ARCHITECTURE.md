# R-32 Architecture

## Overview

The R-32 is an 8-bit CPU with 16 registers. Instructions are 4 bytes long and
follow a RISC-like design.

## Instruction format
31 24 23 20 19 16 15 0
+--------+------+------+----------------------+
| opcode | rd | rs | imm16/imm8 |
+--------+------+------+----------------------+
8 bits 4 bits 4 bits 16 bits

## Registers

| Reg | Name | Purpose |
|-----|------|---------|
| R0  | ZERO | Hardwired to 0 |
| R1  | RA   | Return address / arg 1 |
| R2  | A0   | Arg 2 |
| R3  | A1   | Arg 3 |
| R4-6| T0-T2| Temporaries |
| R7-11| S0-S4| Saved registers |
| R12 | FP   | Frame pointer |
| R13 | SP   | Stack pointer |
| R14 | LR   | Link register |
| R15 | GP   | Global pointer (reserved) |

## Execution flow
┌─────────────┐
│ PC │
└──────┬──────┘
│
┌──────▼──────┐ ┌─────────────┐
│ Instruction│────▶│ Decoder │
│ Memory │ └──────┬──────┘
└─────────────┘ │
▼
┌─────────────┐ ┌─────────────┐
│ Registers │◀───▶│ ALU │
│ (16 × 8) │ └─────────────┘
└─────────────┘
│
▼
┌─────────────┐
│ Data Memory│
└─────────────┘
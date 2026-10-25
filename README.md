# R-32 CPU

A 8-bit CPU with 16 registers, 24 opcodes, a stack, and CALL/RET.

## Structure

- `isa.py` — Frozen ISA (opcodes, registers, format)
- `src/vm.py` — Virtual machine (executes bytecode)
- `src/assembler.py` — Two-pass assembler (labels, directives)
- `src/memory.py` — Memory with bounds checking
- `src/main.py` — Full pipeline (assemble + execute)
- `examples/` — `.r32` programs
- `docs/DECISIONS.md` — Design choices

## Run a program

```bash
python src/main.py

## Requirements
Python 3.10+. No external dependencies.
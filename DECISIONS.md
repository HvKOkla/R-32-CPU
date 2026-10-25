# Design Decisions — R-32 CPU

## 1. Why 16 registers?

- 8 registers is too few: you run out of space quickly.
- 32 registers is too heavy: the opcode becomes too large to decode (5 bits per register).
- 16 registers is the right middle ground (4 bits per register).
- Therefore: **16 registers (R0 to R15)**.

## 2. Why 4 bytes per instruction?

- 2 bytes felt too small: not enough room for opcode + arguments + immediate.
- 8 bytes could cause bugs if not handled carefully (memory waste, more complex addressing).
- 4 bytes is the right compromise.
- Layout: `[opcode][rd][rs][imm8]`.
- Therefore: **4 bytes per instruction**.

## 3. Why little-endian?

- Like x86 and RISC-V: it's the standard, more or less.
- Least significant bytes first is simpler for 16-bit addresses (the last 2 bytes).
- Therefore: **little-endian**.

## 4. Why R0 hardwired to 0?

- Like RISC-V.
- Allows simple no-op instructions (`ADD R0, R0`).
- Simplifies the hardware: no physical register for R0.

## 5. Why flags Z/N/C/V?

- Z (zero): essential for conditional jumps (`JZ`).
- N (negative): for signed comparisons (future `JLT`, `JGT`).
- C (carry): reserved for multi-byte operations.
- V (overflow): reserved for signed operations.
- Therefore: **4 flags, 2 currently used**.

## 6. Why CALL/RET via R14 (LR)?

- Like ARM and RISC-V: R14 = LR (link register).
- No hardware stack (too complex for a pedagogical CPU).
- The stack is managed in software via R13 (SP).
- Therefore: **CALL saves PC to R14, RET jumps to R14**.

## 7. Why `PRINT` as an opcode (and not a directive)?

- It's a pedagogical extension, not a real hardware opcode.
- On a real CPU, `PRINT` would go through a peripheral (MMIO).
- Here, it's a shortcut to see the result.
- Therefore: **`PRINT` = opcode 0x01 (pedagogical, to be replaced by MMIO later)**.
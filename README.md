
```html
<div align="center">
  <img src="docs/R32.svg" alt="R-32 CPU Logo" width="250"/>
  
  <h1>R-32 CPU</h1>
  
  <p><b>An open-source, pedagogical 8-bit CPU with its own ISA, VM, and assembler.</b></p>
  
  <p>
    <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT License">
    <img src="https://img.shields.io/badge/Architecture-8--bit-orange?style=for-the-badge" alt="8-bit">
    <img src="https://img.shields.io/badge/FPGA-In_Progress-yellow?style=for-the-badge" alt="FPGA">
  </p>
</div>

---

## 📖 Overview

The **R-32** is a complete 8-bit computer architecture designed from scratch. It includes a frozen Instruction Set Architecture (ISA), a Python-based Virtual Machine (VM), and a two-pass assembler with label resolution.

The goal of this project is to understand computer architecture from the ground up, culminating in a future hardware implementation on an FPGA (using Amaranth HDL).

## ✨ Features

- **16 Registers**: `R0` (hardwired to 0), `R13` (Stack Pointer), `R14` (Link Register).
- **24 Opcodes**: Full ALU support (ADD, SUB, AND, OR, XOR, SHL, SHR), memory operations (LOAD, STORE), and control flow (JZ, JNZ, JN, JMP, CALL, RET).
- **4-byte fixed instructions**: `[opcode][rd][rs][imm8]` format (Little-endian).
- **Hardware Stack**: Software-managed stack with `PUSH` and `POP`.
- **Flags**: Zero (Z), Negative (N), Carry (C), and Overflow (V).

## 🧠 Register File

The R-32 features 16 general-purpose 8-bit registers. Some have specific roles defined by the ABI (Application Binary Interface) for future software conventions.

| Register | Alias | Purpose | Notes |
| :---: | :---: | :--- | :--- |
| **R0** | `ZERO` | Zero Register | **Hardwired to 0.** Writes are ignored. |
| **R1** | `RA` | Return Address | Arg 1 (Future: used by CALL/RET) |
| **R2** | `A0` | Argument 0 | Arg 2 |
| **R3** | `A1` | Argument 1 | Arg 3 |
| **R4-R6** | `T0-T2` | Temporaries | Caller-saved. Used for local computations. |
| **R7-R11**| `S0-S4` | Saved Registers | Callee-saved. Must be preserved across function calls. |
| **R12** | `FP` | Frame Pointer | Points to the base of the current stack frame. |
| **R13** | `SP` | Stack Pointer | Points to the top of the stack. Grows downwards. |
| **R14** | `LR` | Link Register | Holds the return address during `CALL`. |
| **R15** | `GP` | Global Pointer | Reserved for global data access (future). |

## ⚙️ Instruction Set (ISA v1.0)

The CPU uses a fixed 4-byte instruction format: `[opcode (8 bits)][rd (4 bits)][rs (4 bits)][imm8 (8 bits)]`. 
For jump instructions, the address is encoded on 16 bits across the `rs` and `imm` fields (Little-Endian).

| Opcode | Mnemonic | Arguments | Description | Flags |
| :---: | :--- | :--- | :--- | :--- |
| `0x00` | **HALT** | - | Stops execution. | - |
| `0x01` | **PRINT** | `Rd` | Prints the value of register `Rd`. (Pedagogical) | - |
| `0x02` | **MOV** | `Rd, imm8` | Loads immediate value into `Rd`. | - |
| `0x03` | **ADD** | `Rd, Rs` | `Rd = Rd + Rs` | Z, N, C |
| `0x04` | **SUB** | `Rd, Rs` | `Rd = Rd - Rs` | Z, N, C |
| `0x05` | **CMP** | `Ra, Rb` | Compares `Ra` and `Rb` (subtracts without storing). | Z, N, C |
| `0x06` | **JZ** | `addr16/label` | Jump if Zero flag is set. | - |
| `0x07` | **JMP** | `addr16/label` | Unconditional jump. | - |
| `0x08` | **LOAD** | `Rd, addr8` | `Rd = mem[addr8]` | - |
| `0x09` | **STORE** | `Rd, addr8` | `mem[addr8] = Rd` | - |
| `0x0A` | **NOP** | - | No operation. | - |
| `0x0B` | **AND** | `Rd, Rs` | `Rd = Rd AND Rs` | Z, N |
| `0x0C` | **OR** | `Rd, Rs` | `Rd = Rd OR Rs` | Z, N |
| `0x0D` | **XOR** | `Rd, Rs` | `Rd = Rd XOR Rs` | Z, N |
| `0x0E` | **SHL** | `Rd, Rs` | `Rd = Rd << Rs` (Shift Left) | Z, N |
| `0x0F` | **SHR** | `Rd, Rs` | `Rd = Rd >> Rs` (Shift Right) | Z, N |
| `0x10` | **JNZ** | `addr16/label` | Jump if Zero flag is **not** set. | - |
| `0x11` | **JN** | `addr16/label` | Jump if Negative flag is set. | - |
| `0x12` | **PUSH** | `Rd` | Pushes `Rd` onto the stack. | - |
| `0x13` | **POP** | `Rd` | Pops the top of the stack into `Rd`. | - |
| `0x14` | **CALL** | `addr16/label` | Pushes PC to `LR` (R14) and jumps. | - |
| `0x15` | **RET** | - | Jumps to the address in `LR` (R14). | - |
| `0x16` | **INC** | `Rd` | `Rd = Rd + 1` | Z, N |
| `0x17` | **DEC** | `Rd` | `Rd = Rd - 1` | Z, N |

## 📂 Project Structure

| Path | Description |
|------|-------------|
| `isa.py` | The frozen Instruction Set Architecture (opcodes, registers, format). |
| `src/vm.py` | The Virtual Machine (executes bytecode). |
| `src/assembler.py` | Two-pass assembler (handles labels, comments, and constants). |
| `src/memory.py` | Memory manager with bounds checking. |
| `src/main.py` | The full pipeline (assemble `.r32` → execute). |
| `examples/` | A collection of `.r32` assembly programs. |
| `docs/` | Design choices, architecture diagrams, and logo. |

## 🚀 Getting Started

### Prerequisites
- Python 3.10 or higher. No external dependencies required.

### Run a program
1. Clone the repository:
   ```bash
   git clone https://github.com/HvKOkla/R-32-CPU.git
   cd R-32-CPU
   ```
2. Choose a program in `src/main.py`:
   ```python
   nom_test = "fibonacci" # or "bubble_sort", "eratosthenes", etc.
   ```
3. Run the pipeline:
   ```bash
   python src/main.py
   ```

## 🎮 Example Programs

The `examples/` folder contains several programs written in R-32 assembly to test the CPU:

- **`test_all.r32`**: A global test suite (ALU, flags, stack, jumps).
- **`fibonacci.r32`**: Computes the first 10 terms of the Fibonacci sequence.
- **`bubble_sort.r32`**: Sorts an array of 4 numbers in memory.
- **`eratosthenes.r32`**: Sieve of Eratosthenes (finds prime numbers).
- **`guess.r32`**: A simple number-guessing game using conditional jumps.

## 🗺️ Roadmap

- [x] Design the ISA (v1.0).
- [x] Implement the Python VM and Assembler.
- [x] Write example programs (Fibonacci, Sort, Sieve, Game).
- [ ] Port the CPU to **Amaranth HDL** (Python).
- [ ] Synthesize and deploy on **Tang Nano 9K FPGA**.
- [ ] Add VGA and PS/2 peripherals.
- [ ] Port Snake to R-32 assembly.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---
<div align="center">
  <i>Built with passion to understand how computers really work.</i>
</div>
```




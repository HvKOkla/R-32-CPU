# R-32 CPU

**Processeur pédagogique 16 bits, conçu pour être implémenté sur FPGA.**

Le R-32 est un CPU RISC-like : 16 registres 16 bits, mémoire 64 Kmots,
instructions à format fixe, entrées/sorties par UART en MMIO.
L'ensemble (assembleur + VM) est écrit en Python et produit directement
des fichiers `.hex` chargeables dans une mémoire FPGA (`$readmemh`).

## Caractéristiques (v3.0)

- 16 registres généralistes 16 bits (R0 est durci à 0)
- 64 Kmots de mémoire (16 bits), adressage direct et indirect
- 29 instructions (dont `TRAP`/`IRET` v3.0), format fixe 32 bits = 2 mots
- Flags Z / N / C / V calculés comme sur un vrai CPU
- **Interruptions** : timer matériel, vecteur configurable, sans nesting
- UART MMIO (`0xF000-0xF002`) + timer (`0xF030-0xF032`) + port debug décimal
- Assembleur : labels, constantes `.equ`, chaînes, littéraux caractères, pseudo-instructions
- **Jinrai** : langage système maison → asm R-32, avec checker impitoyable
  et accès bas niveau (`peek`/`poke`/`asm`/`trap`)
- Sorties : `.bin` (mots 16 bits) et `.hex` (format `$readmemh`)

## Jinrai en 30 secondes

```bash
python jinrai/jinrai.py examples/jinrai/fib.jr -o build/fib.r32
python src/main.py fib          # après avoir copié le .r32 dans examples/
```

```c
fn fib(n) {
    if n < 2 { return n }
    return fib(n - 1) + fib(n - 2)
}
fn main() {
    var i = 0
    while i < 10 { print_dec(fib(i)) i = i + 1 }
    halt()
}
```

Spec complète : [jinrai/JINRAI.md](jinrai/JINRAI.md)

## Démarrage rapide

```bash
python src/main.py fibonacci
```

Pipeline automatique : assemblage `examples/fibonacci.r32` → exécution VM.

## Carte mémoire

| Adresses      | Zone                          |
|---------------|-------------------------------|
| `0x0000-0x7FFF` | RAM programme + données     |
| `0x8000-0x87CF` | **VRAM** texte 80×25 (RAM partagée, 2000 mots) |
| `0x8800-0xEFFF` | RAM libre                    |
| `0xF000`      | UART data (W : émettre / R : recevoir) |
| `0xF001`      | UART status (R : bit0 RX ready, bit1 TX ready) |
| `0xF002`      | Debug décimal (W : affiche la valeur) |
| `0xF030`      | Timer compteur (R)           |
| `0xF031`      | Timer période (W, 0=off) — lève une IRQ |
| `0xF032`      | Vecteur IRQ (W) — partagé par toutes les sources |
| `0xF040/0xF041` | VGA curseur X/Y (W)        |
| `0xF050/0xF051` | PS/2 clavier : scancode / status |
| `0xF060/0xF061` | PS/2 souris : data (3 octets/paquet) / status |

> La VRAM est de la RAM partagée : le CPU y écrit avec STORE, le contrôleur
> VGA la lit pour l'afficher — exactement comme sur un vrai bus. Pas de DMA.

La pile grandit vers le bas à partir de `0xEFFF`.

## Syntaxe assembleur

```asm
.equ UART, 0xF000

    MOV R1, '>'        ; littéral caractère
    STORE R1, UART     ; -> l'UART
    MOV R2, R1         ; copie reg -> reg (MOVRR)
    CLR R3             ; pseudo : XOR R3, R3

msg: .string "help\n"  ; chaîne NUL-terminée
tab: .word 1, 2, 3     ; mots 16 bits
```

Directives : `.equ`, `.word`, `.ascii` (sans NUL), `.string` (NUL terminé),
`.org`, `.align`. Pseudo-instructions : `CLR Rd`.
Sauts et `CALL` acceptent un label ou une adresse immédiate.

## Structure du projet

```
R-32-CPU-main/
├── src/                  # le CPU : isa, assembler, vm, memory, uart, iobus
├── jinrai/               # compilateur Jinrai v1.0 (gelé) : lexer, parser,
│                         # checker impitoyable, codegen — spec : JINRAI.md
├── examples/             # programmes asm (.r32)
├── examples/jinrai/      # programmes Jinrai (.jr)
├── hardware/logisim/     # schéma + guide (table de microcode figée)
├── tools/
│   ├── disasm.py         # désassembleur (round-trip garanti assemble∘disasm = id)
│   ├── r32dbg.py         # débogueur interactif (breakpoints, step, regs, mem)
│   └── hex2logisim.py    # .hex -> ROM Logisim
├── run_tests.bat
└── docs : ARCHITECTURE.md, DECISIONS.md, CHANGELOG.md, jinrai/JINRAI.md
```

## Outils

```bash
python tools/disasm.py build/fibonacci.hex -o recupere.r32  # binaire -> asm
python tools/r32dbg.py build/fibonacci.hex                  # débogueur interactif
python tools/vga_view.py build/vga_demo.hex ecran.png       # capture d'écran VGA
python tools/vga_view.py build/vga_demo.hex --live          # écran temps réel (terminal)
python jinrai/jinrai.py examples/jinrai/fib.jr -o build/fib.r32
```

## Tests

```bash
python src/main.py test_all    # doit afficher 42 puis 42
python src/main.py shell       # mini-shell UART : help / exit
```

## Roadmap FPGA

1. ✅ ISA 16 bits propre, décodage fixe, MMIO (ce dépôt)
2. ✅ **Plan de masse Logisim** : `hardware/logisim/R32_CPU.circ` + `LOGISIM.md`
   (table de microcode figée, câblage par bloc, procédure de test)
3. ⬜ Câbler et valider dans Logisim-evolution (la VM Python est la référence)
4. ⬜ Traduction en Verilog : le `.hex` généré se charge via `$readmemh`
5. ⬜ Carte FPGA (iCEStick / ECP5) : UART réel vers un terminal

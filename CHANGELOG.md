# Changelog R-32

## v1.0 — version initiale
- ISA 8 bits : 20 instructions, registres 8 bits, mémoire 64 Ko adressée par octets.
- Instructions codées sur 4 octets : `[opcode][rd][rs][imm8]`.
- Assembleur 2 passes, VM avec flags Z/N.

## v1.1
- Ajouts : `CALL`, `RET`, `PUSH`, `POP`, `READ`, `PRINT_CHAR`, `LOAD_IND`, `STORE_IND`, `CMPI`.
- Nouveau mapping des opcodes (passage à 0x14+).

## v1.2 — correctifs
- **`MOVL` implémenté** (documenté dans le README mais absent de l'ISA) : opcode 0x1D.
- **`READ` corrigé** : consommation caractère par caractère, CR (13) renvoyé en fin de ligne, 0 à EOF. Rend le shell utilisable.
- **`run_tests.bat` corrigé** : appelait `run_pipeline` (inexistant) au lieu de `run_test`.
- `shell.r32` : gestion de l'entrée vide / EOF (sortie propre).

## v2.0 — passage 16 bits FPGA (RUPTURE de compatibilité)
- **Mémoire 64 Kmots de 16 bits** (au lieu de 64 Ko d'octets).
- **Instruction = 2 mots (32 bits)** : `W0 = [opcode:8 | rd:4 | rs:4]`, `W1 = imm16`. Décodage trivial en Verilog.
- **Registres 16 bits** (peuvent contenir des adresses) ; ALU 16 bits avec wrap.
- **`PRINT`, `PRINT_CHAR`, `READ` supprimés** → **UART MMIO** :
  - `0xF000` UART data (W : émettre / R : recevoir)
  - `0xF001` UART status (bit0 RX ready, bit1 TX ready)
  - `0xF002` debug décimal (écriture = afficher la valeur)
- **Flags C et V calculés pour de vrai** ; nouveaux sauts `JC`, `JV`.
- `MOVL` conservé comme alias de `MOV` (immédiat 16 bits).
- `LOAD`/`STORE`/`MOV` acceptent les **labels** en opérande.
- `.byte` supprimé (mémoire 16 bits) → `.word`.
- L'assembleur produit en plus un **`.hex` au format `$readmemh`** (Verilog/FPGA).
- `shell.r32` réécrit autour de l'UART (`GETC`, `PRINT_STR`).

## v2.1 — ergonomie de l'assembleur
- **`MOV Rd, Rs`** : copie registre → registre (nouvel opcode `MOVRR` 0x1C).
  Fini le `MOV R5, 0 / ADD R5, R1`.
- **Pseudo-instruction `CLR Rd`** (assemble en `XOR Rd, Rd`).
- **Littéraux caractères** : `'A'`, `'\n'`, `'\r'`, `'\t'`, `'\0'`, `'\\'`, `'\''`.
- **Directives chaînes** : `.ascii "text"` et `.string "text"` (NUL terminé) —
  fini les `.word 104, 101, 108, 112, 0`.

## v3.0 — interruptions + langage Jinrai

**ISA v3.0 (RUPTURE) :**
- Nouveaux opcodes : `IRET` (0x1D, retour d'interruption : flags puis PC dépilés),
  `TRAP` (0x1E, interruption logicielle : PC puis flags empilés, saut à imm16).
- **Timer matériel + IRQ** : `0xF030` compteur (R), `0xF031` période (W, 0=désactivé),
  `0xF032` vecteur (W). Une IRQ empile PC+flags et saute au vecteur ; pas de nesting.
- Bus MMIO général (`src/iobus.py`) : UART + timer, extensible.

**Jinrai v0.1 — le langage système (jinrai/) :**
- `fn`, `let`/`var`, `if/else`, `while`, `return`, expressions complètes
  (`+ - * / %`, comparaisons, `and/or/not`), points-virgules optionnels.
- **Bas niveau intégré** : `peek`/`poke` (MMIO), `asm("...")` avec interpolation
  `{var}`, `addr()`, `trap()`/`iret()`, fonctions `naked`.
- **Checker impitoyable** (JR0001-JR0013 + avertissements JR20xx, `--pedantic`) :
  initialisation, immuabilité, débordements constants, division par zéro,
  code inaccessible, pression de registres (≤8), vérification des handlers.
- Convention : args R2/R3, retour R1, **R4-R11 + LR callee-saved**
  (le callee sauvegarde LR — sinon les appels imbriqués bouclent).
- Bibliothèque logicielle émise à la demande : `__jin_mul16`, `__jin_div16`,
  `__jin_read_dec`.
- Exemples : `examples/jinrai/fib.jr`, `guess.jr`, `irq_demo.jr` (handler IRQ
  écrit en Jinrai).

## Jinrai v1.0 — gel du langage + outils du processeur

**Langage stabilisé (v1.0)** : sémantique gelée, évolutions uniquement
additives (tableaux, pointeurs, `for` arrivent plus tard sans casser
l'existant). 17/17 tests (14 asm + 3 Jinrai) + 7/7 rejets du checker.

**Outils (`tools/`) :**
- **`disasm.py`** — désassembleur `.bin`/`.hex` → `.r32`, avec labels
  automatiques et **propriété de round-trip garantie**
  (`assemble(disasm(b)) == b`, vérifié sur les 12 exemples).
- **`r32dbg.py`** — débogueur interactif : breakpoints, step, run,
  inspection registres/flags/mémoire, désassemblage à chaud.
- **`hex2logisim.py`** — conversion `.hex` → ROM Logisim (32 bits/ligne).

## v3.1 — émulateur de périphériques (VGA/PS/2)

**Matériel émulé (`src/periph.py`) :**
- **VGA texte 80×25** : la VRAM (`0x8000-0x87CF`) est de la **RAM partagée**
  — le CPU y écrit, le contrôleur la lit, comme sur un vrai bus (pas de DMA).
  Registres curseur `0xF040/0xF041`. Capture PNG et rendu ANSI.
- **Clavier PS/2** (`0xF050/0xF051`) : scancodes set 1, traduction stdin,
  séquences flèches (E0), IRQ.
- **Souris PS/2** (`0xF060/0xF061`) : paquets 3 octets, injection
  programmable (`iobus.mouse.inject`).
- Les trois sources d'IRQ partagent le vecteur `0xF032` (priorité
  timer > clavier > souris) ; identification logicielle par les status.
- **`tools/vga_view.py`** : capture PNG headless (`--keys`, `--mouse`) et
  affichage terminal temps réel (`--live`, mode raw).
- Démo : `examples/jinrai/vga_demo.jr` (bannière, scancodes affichés en hex,
  curseur souris `#`) — il a fallu découper en fonctions : le checker JR0011
  (pression de registres ≤ 8) l'a imposé, et c'est la bonne discipline.

**Correctifs :**
- Compilateur Jinrai : fuite de temporaires dans les appels imbriqués en
  argument (les args sont maintenant libérés avant le `CALL`, LIFO strict).
- `feed_char` n'interprète plus les lettres majuscules comme des flèches
  (sur un vrai PS/2, Shift+A envoie le scancode de `a`).
- Checker : les paramètres sont mutables (copies locales, standard C/Rust).

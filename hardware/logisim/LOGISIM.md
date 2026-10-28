# Guide Logisim-evolution — R-32 v2.1

Ce document est la **spécification figée** du moteur R-32. Le fichier
`R32_CPU.circ` contient le plan de masse (composants placés et étiquetés
par zone) ; ce guide donne le câblage exact et la table de microcode.

## 1. Installation et ouverture

1. Télécharger Logisim-evolution : https://github.com/logisim-evolution/logisim-evolution/releases
2. Ouvrir `hardware/logisim/R32_CPU.circ`
3. Trois fenêtres utiles : Simulate > Tick Frequency (1 Hz pour débuter),
   le chronogramme (Window > Timing Diagram) et la vue des valeurs (Poke Tool)

## 2. Charger un programme

```bash
python src/main.py fibonacci                # produit build/fibonacci.hex
python tools/hex2logisim.py build/fibonacci.hex   # -> build/fibonacci_logisim.hex
```

Dans Logisim : clic droit sur **ROM programme** > *Load Image* > choisir
`build/fibonacci_logisim.hex`. Chaque ligne = 1 instruction 32 bits.

## 3. Convention PC

Dans le schéma, le **PC compte les instructions** (0, 1, 2…), pas les mots.
`PC_mots = 2 × PC_logisim`. C'est pourquoi la ROM est large de 32 bits et
le « PC + 1 » ajoute 1 (et non 2).

## 4. Décodage (sortie du splitter)

```
W0 = [opcode:8 | rd:4 | rs:4]    W1 = imm16
opcode = W0[7:0]   rd = W0[11:8]   rs = W0[15:12]   imm16 = W1
```

## 5. ROM de contrôle — table de microcode (à recopier telle quelle)

ROM 256×24. Adresse = opcode (sur 8 bits). Contenu = mot de contrôle (24 bits, hex).

| Adr | Instr | Mot 24 bits | Adr | Instr | Mot 24 bits |
|-----|-------|-------------|-----|-------|-------------|
| 00 | HALT     | `080000` | 0E | STORE     | `002000` |
| 01 | MOV      | `000C00` | 0F | LOAD_IND  | `005900` |
| 02 | ADD      | `101800` | 10 | STORE_IND | `002100` |
| 03 | SUB      | `201800` | 11 | JMP       | `050000` |
| 04 | CMP      | `201000` | 12 | JZ        | `050000` |
| 05 | CMPI     | `201400` | 13 | JNZ       | `050000` |
| 06 | AND      | `301800` | 14 | JN        | `050000` |
| 07 | OR       | `401800` | 15 | JC        | `050000` |
| 08 | XOR      | `501800` | 16 | JV        | `050000` |
| 09 | SHL      | `601800` | 17 | CALL      | `058800` |
| 0A | SHR      | `701800` | 18 | RET       | `020000` |
| 0B | INC      | `101C00` | 19 | PUSH      | `202E68` |
| 0C | DEC      | `201C00` | 1B | NOP       | `000000` |
| 0D | LOAD     | `004800` | 1C | MOVRR     | `000800` |

(POP 0x1A : voir §9 — seule instruction à 2 cycles.)

## 6. Format du mot de contrôle (24 bits)

```
[23:20] alu_op    0=PASS B  1=ADD  2=SUB  3=AND  4=OR  5=XOR  6=SHL  7=SHR
[19]    halt      1 = ne pas charger le PC (processeur arrêté)
[18]    branch    1 = saut conditionnel (décision via la logique de branchement)
[17:16] pc_src    00=PC+1  01=imm16  10=LR        (sélection du MUX PC suivant)
[15:14] wb_sel    00=ALU  01=RAM données  10=PC+1 (sélection du MUX write-back)
[13]    we_mem    écriture RAM données
[12]    we_flags  chargement du registre ZNVC
[11]    we_regfile écriture banc de registres (bloquée si adr W == 0)
[10]    alu_b_sel 0=rb  1=imm16
[9:8]   mem_addr  00=imm16  01=rb  10=sortie ALU
[7:6]   ra_addr   00=rd  01=SP  10=LR
[5:4]   rb_addr   00=rs  01=SP  10=rd
[3]     wr_addr   0=rd  1=SP
```

## 7. Câblage par bloc

**FETCH**
- CLK → PC (horloge) et à tous les composants clockés
- PC.Q → ROM programme (A) ; ROM.D → splitter → opcode/rd/rs/imm16
- MUX PC suivant : entrée 00 = sortie « PC + 1 » (Adder, B = constante 1) ;
  01 = imm16 ; 10 = sortie A du banc quand adr A = LR
- Le MUX est sélectionné par pc_src **uniquement si** `branch=1` et
  `cond_ok=1`, ou si l'opcode est JMP/CALL (voir §8) ; sinon PC+1.
- HALT : `we_pc = NOT halt` sur l'enable du PC.

**BANC DE REGISTRES** (2 RAM 16×16, écriture commune = 2 ports de lecture)
- RAM A : A ← MUX ra_addr (00=rd, 01=const 13, 10=const 14), D ← MUX write-back,
  sel ← we_regfile AND (adr W ≠ 0), clk ← CLK
- RAM B : A ← MUX rb_addr (00=rs, 01=const 13, 10=rd), mêmes D/sel/clk
- Sorties : ra (port A) et rb (port B)

**ALU** — opérande A = ra ; opérande B = MUX (rb / imm16) selon alu_b_sel
- Adder, Subtractor, AND, OR, XOR (largeur 16), 2 Shifter (SHL : logical left,
  SHR : logical right, distance = rb[3:0])
- MUX résultat 8→1 sélectionné par alu_op[2:0]
- Flags : V (Adder/Subtractor : retenue/signe incohérent — voir note) ;
  C = c_out (ADD) / retenue (SUB) ; Z = NOR des 16 bits du résultat ;
  N = résultat[15] ; chargés quand we_flags=1

**RAM DONNÉES** (16×16)
- A ← MUX mem_addr (imm16 / rb / sortie ALU) ; D ← ra ; WE ← we_mem ; sel ← 1
- Sortie D → MUX write-back (entrée 01)

**WRITE-BACK** — MUX wb_sel : 00 = ALU, 01 = RAM, 10 = « PC + 1 » → D des deux RAM regs

## 8. Logique de branchement (zone 2)

Decoder 4 bits sur `opcode[3:0]`, sorties 1..6 actives pour les sauts :

```
cond_ok = S1                (JMP 0x11)
        | S2 & Z            (JZ  0x12)
        | S3 & NOT Z        (JNZ 0x13)
        | S4 & N            (JN  0x14)
        | S5 & C            (JC  0x15)
        | S6 & V            (JV  0x16)
pc_load = branch & cond_ok
sélection MUX PC = pc_src si pc_load, sinon 00 (PC+1)
```

## 9. POP et le cycle de trop

POP fait deux effets (R_dest ← mem[SP] **et** SP ← SP+1) mais le banc n'a
qu'un port d'écriture. Deux options :

- **Option A (recommandée)** : POP = 2 coups d'horloge via une mini-FSM
  (2 états : état 1 = `we_rf, wb=RAM, mem_addr=SP` ; état 2 = `we_rf, wr_addr=SP,
  alu_op=ADD, ra_addr=SP, bsel=imm(1)`). La FSM avance quand opcode == 0x1A.
- **Option B** : sur FPGA, ajouter un second port d'écriture au banc
  (8 registres en bascules + RAM pour le reste) — pas nécessaire ici.

**Note v3.0 (convention d'appel Jinrai) :** le callee sauvegarde aussi **LR
(R14)** dans son prologue (`PUSH R14` après les autres, `POP R14` juste avant
`RET`). Sans ça, les appels imbriqués écrasent l'adresse de retour — bug
classique constaté sur la récursion de fib.

CALL et PUSH restent **monocycles** grâce aux champs ra_addr/rb_addr/wr_addr
du mot de contrôle (voir la table).

## 10. MMIO

Dans Logisim, pour visualiser : décodeur qui teste `adr >= 0xF000`, et un
Hex Digit Display écrit quand `adr == 0xF002` (debug décimal). L'UART réel
viendra plus tard (FPGA) ; la VM Python reste le modèle de référence.

## 11. Procédure de test

1. Charger `fibonacci_logisim.hex` dans la ROM programme
2. Tick à 1 Hz : observer PC (0,1,2…) et le registre R1 (doit afficher
   0, 1, 1, 2, 3, 5, 8, 13, 21, 34 sur le debug décimal)
3. `shell_logisim.hex` : taper `help` dans le Terminal (I/O) si l'UART est câblé,
   sinon vérifier les drapeaux et les sauts JZ/JNZ
4. Comparer chaque instruction avec `src/vm.py` — c'est la référence cycle par cycle

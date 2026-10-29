# Jinrai — langage système pour R-32 (迅雷, « coup de foudre »)

> **STABILITÉ : Jinrai est gelé en v1.0.** Le langage ne change plus de
> sémantique ; les futures additions (tableaux, pointeurs, `for`, …) sont
> **strictement additives**. L'ISA R-32 reste figée elle aussi — le
> compilateur absorbe toute l'évolution pour que le hardware n'en subisse
> aucune. Voir DECISIONS.md #13.

Jinrai compile vers l'assembleur R-32. La chaîne complète :

```
source.jr --[jinrai]--> prog.r32 --[assembler]--> prog.bin + prog.hex --[vm]--> exécution
```

## Usage

```bash
python jinrai/jinrai.py examples/jinrai/fib.jr -o build/fib.r32   # compilation
python jinrai/jinrai.py prog.jr --pedantic                      # warnings = erreurs
```

## Syntaxe

```c
// commentaire ligne   /* bloc */

fn fib(n) {                    // fn [nom]([paramètres]) { ... }
    if n < 2 { return n }      // if / else, while, return (point-virgule optionnel)
    return fib(n - 1) + fib(n - 2)
}

naked fn handler() {           // naked = pas de prologue (handler IRQ/TRAP)
    asm("PUSH R1")
    asm("LOAD R1, {compteur}") // interpolation de variable possible
    iret()
}

fn main() {
    let a = 42                 // immutable
    var b = 0                  // mutable
    b = b + 1
    while b < 10 { print_dec(b) }
    halt()
}
```

Types : entiers 16 bits (0..65535, wrapping). Expressions : `+ - * / %`,
comparaisons `== != < > <= >=`, `and or not` (bitwise pour and/or),
parenthèses, littéraux `0x`, `0b`, décimal, caractères `'A' ` `'\n'`.

## Convention d'appel

| Rôle | Registre |
|---|---|
| Argument 1 / 2 | R2 (A0) / R3 (A1) — **max 2 paramètres** |
| Valeur de retour | R1 (RA) |
| Scratch (écrasés par tout appel) | R1, R2, R3 |
| Callee-saved | **R4-R11 ET LR (R14)** — le callee pousse/pope ce qu'il utilise |

Les variables locales vivent dans R4+, les temporaries d'expression au-dessus.
Le checker garantit : `locaux + pression_max ≤ 8`.

## Builtins

| Instruction | Effet |
|---|---|
| `peek(a)` | lit mem[a] (expression) |
| `poke(a, v)` | écrit mem[a] = v |
| `print("texte\n")` | chaîne sur l'UART |
| `print_dec(v)` | valeur décimale sur le port debug (0xF002) |
| `putc(c)` / `getc()` / `read_dec()` | UART caractère / nombre saisi |
| `halt()` | arrête le CPU |
| `trap(handler)` / `iret()` | interruption logicielle v3.0 (handler = naked fn) |
| `addr(fonction)` | adresse d'un label |
| `asm("...")` | assembleur inline verbatim, `{var}` interpolé |

## Le checker impitoyable

**Impitoyable au compile-time, pour que le run-time soit silencieux.**
Sur un CPU sans MMU, un crash n'explique rien : le refus de compilation, si.

| Code | Erreur |
|---|---|
| JR0001 | variable déjà déclarée (pas de shadowing) |
| JR0002 | nom inconnu |
| JR0003 | utilisée avant initialisation |
| JR0004 | assignation d'un `let` |
| JR0005 | fonction inconnue |
| JR0006 | mauvais nombre d'arguments |
| JR0007 | littéral/expression constante hors plage i16 |
| JR0008 | division par zéro constante |
| JR0009 | code inaccessible après return |
| JR0010 | fonction à valeur sans return final |
| JR0011 | pression registres > 8 (R4-R11) |
| JR0012 | naked : seuls asm/iret/halt autorisés |
| JR0013 | TRAP vers une fonction non-naked |
| JR20xx | avertissements (variable/paramètre/fonction inutilisé, résultat ignoré) — `--pedantic` les promeut en erreurs |

## Limites assumées (v0.1)

- max 2 paramètres, max 8 registres locaux+temporaires par fonction
- pas de tableaux, pointeurs ni chaînes dans les expressions (arrivent en v0.2)
- `and`/`or` sont bitwise (pas de court-circuit)
- mult/div logicielles (additions/soustractions répétées)

#!/usr/bin/env python3
"""
Jinrai — compilateur R-32 v3.0.

Usage :
  python jinrai/jinrai.py <source.jr> [-o <sortie.r32>] [--pedantic]

Pipeline : lexer -> parser -> checker impitoyable -> codegen (.r32).
La sortie s'assemble ensuite avec src/assembler.py comme n'importe quel .r32.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lexer import JinraiError          # noqa: E402
from parser import parse              # noqa: E402
from checker import check             # noqa: E402
from codegen import generate          # noqa: E402


def compile_file(src_path, out_path, pedantic=False):
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()
    program = parse(src)
    fns, warnings = check(program, pedantic=pedantic)
    for w in warnings:
        print(w, file=sys.stderr)
    asm_src = generate(program, fns, warnings)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(asm_src)
    n_fn = len(fns)
    print(f"Jinrai : {n_fn} fonction(s), {len(asm_src.splitlines())} lignes d'asm -> {out_path}")


def main():
    ap = argparse.ArgumentParser(prog="jinrai", description="Compilateur Jinrai -> R-32 asm")
    ap.add_argument("source", help="fichier source .jr")
    ap.add_argument("-o", "--output", default=None, help="sortie .r32 (défaut : <source>.r32)")
    ap.add_argument("--pedantic", action="store_true",
                    help="promouvoir les avertissements en erreurs")
    args = ap.parse_args()

    out = args.output or os.path.splitext(args.source)[0] + ".r32"
    try:
        compile_file(args.source, out, pedantic=args.pedantic)
    except JinraiError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"erreur[JR0000] : {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

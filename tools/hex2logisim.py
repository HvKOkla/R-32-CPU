#!/usr/bin/env python3
"""
hex2logisim.py — convertit un .hex R-32 (1 mot 16 bits par ligne) en
fichier chargeable dans la ROM programme de Logisim (1 instruction 32
bits par ligne : W0 puis W1 fusionnés, W0 en poids faible).

Usage : python tools/hex2logisim.py build/fibonacci.hex
Sortie: build/fibonacci_logisim.hex
"""
import sys
import os

def main():
    if len(sys.argv) != 2:
        print("Usage: hex2logisim.py <fichier.hex>")
        sys.exit(1)
    src = sys.argv[1]
    words = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                words.append(int(line, 16))
    if len(words) % 2 != 0:
        words.append(0)  # complète la dernière instruction
    dst = os.path.splitext(src)[0] + "_logisim.hex"
    with open(dst, "w", encoding="utf-8") as f:
        for i in range(0, len(words), 2):
            w0, w1 = words[i], words[i + 1]
            f.write(f"{(w1 << 16) | w0:08x}\n")
    print(f"{dst} : {len(words) // 2} instructions générées")

if __name__ == "__main__":
    main()

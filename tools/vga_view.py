#!/usr/bin/env python3
"""
vga_view.py — visualiseur VGA pour la VM R-32 v3.1.

Deux modes :

  1. CAPTURE (headless) : exécute un programme, puis écrit un PNG de l'écran.
     python tools/vga_view.py build/demo.hex build/screen.png [--steps N]
         [--keys "abc"] [--mouse dx,dy,boutons]...

  2. LIVE (terminal) : écran ANSI temps réel + clavier PS/2 (mode raw).
     python tools/vga_view.py build/demo.hex --live
     Ctrl-C pour quitter. (Souris : périphérique injectable en mode capture.)

Sans --live : capture PNG (défaut : exécution jusqu'au HALT ou 100000 pas).
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from vm import R32VM          # noqa: E402
from disasm import load_words  # noqa: E402


def parse_keys(spec):
    """'aZ\\x1b' -> événements clavier ; flèches : ^A^B^C^D = haut/bas/droite/gauche."""
    events = []
    for ch in spec:
        if ch == '^':  # les ^X encodés par paires
            continue
        events.append(ch)
    return spec  # l'injection interprète les caractères un par un


def run_capture(path, out_png, max_steps, keys, mouse_moves):
    vm = R32VM()
    vm.load_program(load_words(path))

    # injection des entrées AVANT l'exécution (le programme les lira ensuite)
    for ch in keys:
        if ch == '\x1b':
            vm.iobus.kbd.feed_char('\x1b')
        elif ch == '\x00':
            continue
        else:
            vm.iobus.kbd.feed_char(ch)
    for (dx, dy, btn) in mouse_moves:
        vm.iobus.mouse.inject(dx, dy, btn)

    steps = 0
    while not vm.halted and steps < max_steps:
        vm.step()
        steps += 1
    vm.iobus.vga.render_png(out_png)
    print(f"{out_png} : {steps} cycles, écran capturé")


def run_live(path):
    import termios
    import tty

    vm = R32VM()
    vm.load_program(load_words(path))
    old = termios.tcgetattr(sys.stdin)
    print("\x1b[2J\x1b[?25l", end="", flush=True)  # efface, cache le curseur
    try:
        tty.setraw(sys.stdin.fileno())
        while not vm.halted:
            for _ in range(2000):        # ~un quantum d'affichage
                if vm.halted:
                    break
                vm.step()
            lines = vm.iobus.vga.render_lines()
            out = ["\x1b[H"]             # curseur en haut à gauche
            out.append("\x1b[48;5;17m")  # fond bleu nuit
            for line in lines:
                out.append(line + " " * (80 - len(line)))
                out.append("\n")
            out.append("\x1b[0m")
            sys.stdout.write("".join(out))
            sys.stdout.flush()
            time.sleep(1 / 30)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.fileno(), termios.TCSADRAIN)
        print("\x1b[0m\x1b[2J\x1b[?25h", end="", flush=True)


def main():
    ap = argparse.ArgumentParser(prog="vga_view")
    ap.add_argument("programme", help=".hex ou .bin")
    ap.add_argument("sortie", nargs="?", default="screen.png", help="PNG (mode capture)")
    ap.add_argument("--live", action="store_true", help="affichage terminal temps réel")
    ap.add_argument("--steps", type=int, default=100000, help="budget de cycles (capture)")
    ap.add_argument("--keys", default="", help="frappes à injecter (avant l'exécution)")
    ap.add_argument("--mouse", default="",
                    help="mouvements dx,dy,boutons;dx,dy,boutons (capture)")
    args = ap.parse_args()

    mouse_moves = []
    if args.mouse:
        for mv in args.mouse.split(";"):
            dx, dy, btn = (int(x) for x in mv.split(","))
            mouse_moves.append((dx, dy, btn))

    if args.live:
        run_live(args.programme)
    else:
        run_capture(args.programme, args.sortie, args.steps, args.keys, mouse_moves)


if __name__ == "__main__":
    main()

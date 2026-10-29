"""
UART MMIO pour la VM R-32 v2.0.

Émule le futur périphérique UART (type 16550 simplifié) qui sera
décodé en dur sur FPGA à l'adresse MMIO_BASE (voir isa.py).

Registres :
  +0 (UART_DATA)   : W -> émet le caractère (8 bits de poids faible)
                     R -> caractère reçu (0 si aucun / EOF)
  +1 (UART_STATUS) : R -> bit0 = caractère disponible, bit1 = TX libre
  +2 (DEBUG_DEC)   : W -> affiche la valeur en décimal (débogage)
"""

import sys

from isa import UART_DATA, UART_STATUS, DEBUG_DEC


class UART:
    def __init__(self):
        self._buf = ""          # caractères de la ligne en cours
        self._line_done = False # un CR (13) doit encore être renvoyé
        self._eof = False
        self._tty = sys.stdin.isatty()

    # --- côté émission ---
    def _write_data(self, value):
        print(chr(value & 0xFF), end="", flush=True)

    def _write_decimal(self, value):
        print(value & 0xFFFF, flush=True)

    # --- côté réception ---
    def _fill(self):
        """Lit une ligne depuis stdin (bloque sur TTY, EOF sur pipe)."""
        try:
            self._buf = input()
        except EOFError:
            self._eof = True

    def _next_char(self):
        """Prochain caractère, ou None si rien n'est disponible."""
        if self._line_done:
            self._line_done = False
            return 13  # CR : fin de la ligne précédente
        if not self._buf:
            return None
        ch = self._buf[0]
        self._buf = self._buf[1:]
        if ch == "\n":
            return 13  # le retour à la ligne EST le marqueur de fin
        if not self._buf:
            self._line_done = True
        return ord(ch)

    def _available(self):
        if self._line_done or self._buf or self._eof:
            return True
        if self._tty:
            return True  # optimiste : la lecture bloquera sur input()
        self._fill()
        return bool(self._line_done or self._buf or self._eof)

    # --- interface MMIO ---
    def read_reg(self, offset):
        if offset == UART_STATUS - UART_DATA:
            return 1 if self._available() else 0
        if offset == UART_DATA - UART_DATA:
            ch = self._next_char()
            if ch is None:
                if self._eof:
                    return 0
                self._fill()
                ch = self._next_char()
            return ch if ch is not None else 0
        return 0

    def write_reg(self, offset, value):
        if offset == UART_DATA - UART_DATA:
            self._write_data(value)
        elif offset == DEBUG_DEC - UART_DATA:
            self._write_decimal(value)
        # les écritures sur les autres offsets sont ignorées

"""
Mémoire R-32 v2.0 : 64 Kmots de 16 bits + espace MMIO.

Carte :
  0x0000 - 0xEFFF  RAM (le programme doit tenir dans cette zone)
  0xF000 - 0xFFFF  Périfériques MMIO (délégués à l'objet `mmio`,
                   typiquement un UART — voir uart.py)
"""

from isa import MMIO_BASE, WORD_MASK


class MemoryManager:
    VRAM_START = MMIO_BASE  # 0xF000
    STACK_TOP  = 0xEFFF
    MAX_SIZE   = 0x10000

    def __init__(self, size=MAX_SIZE, mmio=None):
        if size <= 0 or size > self.MAX_SIZE:
            raise ValueError("Taille mémoire invalide (1..65536 mots)")
        self.size = size
        self.memory = [0] * size
        self.mmio = mmio

    def _is_mmio(self, address):
        return self.VRAM_START <= address < self.size

    def _check(self, address, length=1):
        if not isinstance(address, int):
            raise TypeError(f"Adresse non entière : {address!r}")
        if not (0 <= address < self.size):
            raise IndexError(
                f"Adresse {hex(address)} hors limites [0, {hex(self.size - 1)}]"
            )
        if address + length > self.size:
            raise IndexError(
                f"Débordement mémoire : {length} mot(s) à partir de {hex(address)}"
            )

    def read(self, address):
        if self._is_mmio(address):
            if self.mmio is None:
                return 0
            return self.mmio.read_reg(address - self.VRAM_START) & WORD_MASK
        self._check(address, 1)
        return self.memory[address]

    def write(self, address, value):
        if self._is_mmio(address):
            if self.mmio is not None:
                self.mmio.write_reg(address - self.VRAM_START, value)
            return
        self._check(address, 1)
        self.memory[address] = value & WORD_MASK

    def load_program(self, bytecode, start_address=0):
        """Charge un programme (liste de mots 16 bits) en RAM."""
        if not bytecode:
            return
        self._check(start_address, len(bytecode))
        if start_address + len(bytecode) > self.VRAM_START:
            raise IndexError(
                f"Le programme déborde sur la zone MMIO "
                f"(fin à {hex(start_address + len(bytecode))} >= {hex(self.VRAM_START)})"
            )
        for i, word in enumerate(bytecode):
            self.memory[start_address + i] = word & WORD_MASK

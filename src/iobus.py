"""
Bus MMIO R-32 v3.1 — dispatch les accès 0xF000-0xFFFF vers les périphériques.

Carte :
  0xF000-0xF002  UART (voir uart.py)
  0xF030-0xF032  Timer + IRQ (v3.0)
  0xF040-0xF041  VGA curseur (v3.1) — la VRAM 0x8000+ est de la RAM partagée
  0xF050-0xF051  PS/2 clavier (v3.1)
  0xF060-0xF061  PS/2 souris (v3.1)

IRQ : les sources (timer, clavier, souris) partagent le vecteur 0xF032 ;
le logiciel identifie la source via les registres status.
"""

from uart import UART
from periph import VGAText, PS2Keyboard, PS2Mouse


class Timer:
    """Timer à période fixe. Chaque `tick()` = un cycle processeur."""

    def __init__(self):
        self.count = 0
        self.period = 0      # 0 = désactivé
        self.vector = 0      # adresse du handler
        self._pending = False

    def tick(self):
        if self.period:
            self.count += 1
            if self.count >= self.period:
                self.count = 0
                self._pending = True

    def take_pending(self):
        p, self._pending = self._pending, False
        return p

    def read_reg(self, offset):
        if offset == 0:
            return self.count
        return 0

    def write_reg(self, offset, value):
        if offset == 1:
            self.period = value & 0xFFFF
        elif offset == 2:
            self.vector = value & 0xFFFF


class IOBus:
    """Distribue les accès MMIO. Même interface que l'UART seul historique."""

    def __init__(self):
        self.uart = UART()
        self.timer = Timer()
        self.vga = VGAText()
        self.kbd = PS2Keyboard()
        self.mouse = PS2Mouse()

    def attach_mem(self, mem):
        """La VGA lit la VRAM en RAM partagée (comme le ferait le hardware)."""
        self.vga.attach_mem(mem)

    # --- dispatch ---
    def read_reg(self, offset):
        if offset <= 2:
            return self.uart.read_reg(offset)
        if 0x30 <= offset <= 0x32:
            return self.timer.read_reg(offset - 0x30)
        if 0x40 <= offset <= 0x41:
            return self.vga.read_reg(offset - 0x40)
        if 0x50 <= offset <= 0x51:
            if offset == 0x50:
                return self.kbd.read_data()
            return self.kbd.read_reg(offset - 0x50)
        if 0x60 <= offset <= 0x61:
            if offset == 0x60:
                return self.mouse.read_data()
            return self.mouse.read_reg(offset - 0x60)
        return 0

    def write_reg(self, offset, value):
        if offset <= 2:
            self.uart.write_reg(offset, value)
        elif 0x30 <= offset <= 0x32:
            self.timer.write_reg(offset - 0x30, value)
        elif 0x40 <= offset <= 0x41:
            self.vga.write_reg(offset - 0x40, value)
        elif 0x50 <= offset <= 0x51:
            self.kbd.write_reg(offset - 0x50, value)
        elif 0x60 <= offset <= 0x61:
            self.mouse.write_reg(offset - 0x60, value)

    # --- cycle ---
    def poll(self):
        """Appelé à chaque cycle : aspirer le clavier (mode interactif)."""
        self.kbd.poll_stdin()

    def take_pending(self):
        """Priorité fixe : timer > clavier > souris. Une IRQ à la fois."""
        if self.timer.take_pending():
            return True
        if self.kbd.take_pending():
            return True
        if self.mouse.take_pending():
            return True
        return False

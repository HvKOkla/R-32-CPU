"""
Périphériques émulés R-32 v3.1 — VGA texte + PS/2 clavier/souris.

Philosophie matérielle : la VRAM (0x8000-0x87CF) est de la RAM partagée —
le CPU y écrit avec STORE/STORE_IND, le contrôleur VGA la lit pour l'afficher,
en parallèle, exactement comme sur un vrai bus. Pas de DMA magique.

Carte MMIO (offsets depuis 0xF000, voir isa.py) :
  0x40/0x41  VGA curseur X / Y (écriture)
  0x50/0x51  PS/2 clavier : data (scancode set 1) / status (bit0 = prêt)
  0x60/0x61  PS/2 souris : data (flux 3 octets/paquet) / status
Les trois sources partagent le vecteur IRQ (0xF032) ; le logiciel identifie
la source en lisant les registres status (classique).
"""

import select
import sys
from collections import deque

# Scancodes PS/2 set 1 (make codes)
_SCAN = {
    'a': 0x1C, 'b': 0x32, 'c': 0x21, 'd': 0x23, 'e': 0x24, 'f': 0x2B,
    'g': 0x34, 'h': 0x33, 'i': 0x43, 'j': 0x3B, 'k': 0x42, 'l': 0x4B,
    'm': 0x3A, 'n': 0x31, 'o': 0x44, 'p': 0x4D, 'q': 0x15, 'r': 0x2D,
    's': 0x1B, 't': 0x2C, 'u': 0x3C, 'v': 0x2A, 'w': 0x1D, 'x': 0x22,
    'y': 0x35, 'z': 0x1A,
    '0': 0x45, '1': 0x16, '2': 0x1E, '3': 0x26, '4': 0x25, '5': 0x2E,
    '6': 0x36, '7': 0x3D, '8': 0x3E, '9': 0x46,
    ' ': 0x29, '\r': 0x5A, '\n': 0x5A, '\x1b': 0x76, '\x7f': 0x66,
    '\t': 0x0D,
}
# séquences flèches : E0 + code
_SCAN_E0 = {'A': 0x75, 'B': 0x72, 'C': 0x74, 'D': 0x6B}  # haut/bas/droite/gauche


class VGAText:
    """Contrôleur VGA texte 80x25. La VRAM vit en RAM partagée."""

    COLS, ROWS = 80, 25
    VRAM = 0x8000          # 2000 mots : 1 caractère (poids faible) par cellule
    CELLS = COLS * ROWS    # 0x8000 .. 0x87CF

    def __init__(self):
        self.mem = None    # branché par IOBus.attach_mem
        self.cursor_x = 0
        self.cursor_y = 0

    def attach_mem(self, mem):
        self.mem = mem

    def read_reg(self, offset):
        return 0

    def write_reg(self, offset, value):
        if offset == 0:
            self.cursor_x = value % self.COLS
        elif offset == 1:
            self.cursor_y = value % self.ROWS

    def cell(self, x, y):
        return self.mem.read(self.VRAM + y * self.COLS + x) & 0xFF

    def render_lines(self, rstrip=True):
        """Les 25 lignes à l'instant T (pour terminal ANSI ou tests)."""
        lines = []
        for y in range(self.ROWS):
            row = []
            for x in range(self.COLS):
                c = self.cell(x, y)
                if c == 0:
                    c = 32
                row.append(chr(c) if 32 <= c < 127 else chr(0x2593))
            line = "".join(row)
            lines.append(line.rstrip() if rstrip else line)
        return lines

    def render_png(self, path, scale=2):
        """Capture d'écran PNG de l'écran texte."""
        from PIL import Image, ImageDraw, ImageFont
        cw, ch = 9 * scale, 16 * scale
        img = Image.new("RGB", (self.COLS * cw, self.ROWS * ch), (0, 0, 40))
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSansMono.ttf", 13 * scale)
        except OSError:
            font = ImageFont.load_default()
        for y in range(self.ROWS):
            for x in range(self.COLS):
                c = self.cell(x, y)
                if c in (0, 32):
                    continue
                ch_text = chr(c) if 32 <= c < 127 else "?"
                d.text((x * cw + scale, y * ch + scale), ch_text,
                       fill=(190, 200, 230), font=font)
        cx, cy = self.cursor_x, self.cursor_y
        d.rectangle([cx * cw, cy * ch + ch - 3 * scale,
                     cx * cw + cw - 1, cy * ch + ch - 1], fill=(255, 255, 255))
        img.save(path)


class PS2Port:
    """Base PS/2 : file d'octets, bit0 du status = prêt, IRQ quand non vide."""

    def __init__(self):
        self.queue = deque()
        self._pending = False

    def _push_bytes(self, data):
        for b in data:
            self.queue.append(b & 0xFF)
        self._pending = True

    def read_reg(self, offset):
        if offset == 1:  # status
            return 1 if self.queue else 0
        return 0

    def write_reg(self, offset, value):
        pass  # pas de commande émulée (reset/ACK simplifiés)

    def read_data(self):
        if not self.queue:
            return 0
        v = self.queue.popleft()
        if not self.queue:
            self._pending = False
        return v

    def take_pending(self):
        p, self._pending = self._pending, False
        return p


class PS2Keyboard(PS2Port):
    """Clavier PS/2 : traduit stdin en scancodes set 1."""

    def __init__(self):
        super().__init__()
        self._tty = sys.stdin.isatty()

    def feed_char(self, ch):
        """Injecte un caractère (code de la touche, set 1).
        Comme sur le vrai hardware : 'A' (shift+a) envoie le code de 'a'."""
        code = _SCAN.get(ch) or _SCAN.get(ch.lower())
        if code is not None:
            self._push_bytes([code])
        elif ch.isprintable():
            self._push_bytes([ord(ch) & 0xFF])

    def feed_ext(self, code):
        """Scancode étendu (préfixe E0), ex. les flèches."""
        self._push_bytes([0xE0, code])

    def feed_scancode(self, code):
        self._push_bytes([code])

    def poll_stdin(self):
        """Mode interactif : aspirer les touches disponibles (non bloquant)."""
        if not self._tty:
            return
        while True:
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0)
            except (OSError, ValueError):
                return
            if not r:
                return
            ch = sys.stdin.read(1)
            if not ch:
                return
            if ch == '\x1b':  # peut être une flèche : [ A/B/C/D
                seq = ''
                r, _, _ = select.select([sys.stdin], [], [], 0.002)
                if r:
                    seq = sys.stdin.read(2)
                if len(seq) == 2 and seq[0] == '[' and seq[1] in _SCAN_E0:
                    self.feed_ext(_SCAN_E0[seq[1]])
                    continue
                if seq:
                    for c in seq:
                        self.feed_char(c)
                self.feed_char('\x1b')  # ECHAP seul
            else:
                self.feed_char(ch)


class PS2Mouse(PS2Port):
    """Souris PS/2 : paquets 3 octets (boutons/dx/dy), injectables."""

    def inject(self, dx, dy, buttons=0):
        dx = max(-255, min(255, int(dx)))
        dy = max(-255, min(255, int(dy)))
        b0 = 0x08 | (buttons & 0x07)
        if dx < 0:
            b0 |= 0x10
        if dy < 0:
            b0 |= 0x20
        self._push_bytes([b0, dx & 0xFF, dy & 0xFF])

class MemoryManager:
    VRAM_START = 0xF000
    STACK_TOP  = 0xEFFF  

    def __init__(self, size=65536):
        if size <= 0 or size > 0x10000:
            raise ValueError("Taille mémoire invalide (1..65536)")
        self.size = size
        self.memory = [0] * size
        self.vram_start = self.VRAM_START

    
    def _check(self, address, length=1):
        if not isinstance(address, int):
            raise TypeError(f"Adresse non entière : {address!r}")
        if not (0 <= address < self.size):
            raise IndexError(
                f"Adresse {hex(address)} hors limites [0, {hex(self.size - 1)}]"
            )
        if address + length > self.size:
            raise IndexError(
                f"Débordement mémoire : {length} octet(s) à partir de {hex(address)}"
            )

    def read(self, address):
        self._check(address, 1)
        return self.memory[address]

    def write(self, address, value):
        self._check(address, 1)
        self.memory[address] = value & 0xFF

    def read_word(self, address):
        self._check(address, 2)
        return self.memory[address] | (self.memory[address + 1] << 8)

    def write_word(self, address, value):
        self._check(address, 2)
        self.memory[address] = value & 0xFF
        self.memory[address + 1] = (value >> 8) & 0xFF

    def load_program(self, bytecode, start_address=0):
        if not bytecode:
            return
        self._check(start_address, len(bytecode))
        for i, byte in enumerate(bytecode):
            self.memory[start_address + i] = byte & 0xFF
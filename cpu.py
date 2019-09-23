from ctypes import c_uint8 as uint8, \
    c_uint16 as uint16, \
    c_bool

from bus import Bus


"""
Memory Map:
+---------------+= 0xFFF (4095) End of Chip-8 RAM
|               |
|               |
|               |
|               |
|               |
| 0x200 to 0xFFF|
|     Chip-8    |
| Program / Data|
|     Space     |
|               |
+- - - - - - - -+= 0x600 (1536) Start of ETI 660 Chip-8 programs
|               |
|               |
|               |
+---------------+= 0x200 (512) Start of most Chip-8 programs
| 0x000 to 0x1FF|
| Reserved for  |
|  interpreter  |
+---------------+= 0x000 (0) Start of Chip-8 RAM
"""


class CPU:
    __slots__ = (
        "bus",
        "registers",
        "key_input",
        "screen",
        "stack",
        "timer",
        "opcode",
        "instructions",
    )
    _START_PROGRAM_ADDR = uint16(0x200)
    _ETI_PROGRAM_ADDR = uint16(0x600)
    _END_RAM_ADDR = uint16(0xFFF)

    def __init__(self):
        """
        REGISTERS:
        [16 x 8-bit] (V0-F) - general purpose registers
        [1 x 16-bit] (I) - index register
        [1 x 16-bit] (SP) - stack pointer
        [1 x 16-bit] (PC) - program counter
        [1 x 8-bit] (DT) - delay timer
        [1 x 8-bit] (ST) - sound time
        """
        self.bus = Bus(0x0FFF, self)

        self.registers = {
            'V': (uint8 * 16)(),
            'I': uint16(0x0000),
            'SP': uint16(0x0000),
            'PC': uint16(0x0000),
        }

        # TODO: use uint16 insted of (bool * 16) and save key state as single bite
        self.key_input = (c_bool * 16)()
        self.screen = [0] * 64 * 32

        self.stack = []  # ??
        self.timer = {
            "delay": 0,
            "sound": 0
        }

        font = (0xF0, 0x90, 0x90, 0x90, 0xF0,  # 0
                0x20, 0x60, 0x20, 0x20, 0x70,  # 1
                0xF0, 0x10, 0xF0, 0x80, 0xF0,  # 2
                0xF0, 0x10, 0xF0, 0x10, 0xF0,  # 3
                0x90, 0x90, 0xF0, 0x10, 0x10,  # 4
                0xF0, 0x80, 0xF0, 0x10, 0xF0,  # 5
                0xF0, 0x80, 0xF0, 0x90, 0xF0,  # 6
                0xF0, 0x10, 0x20, 0x40, 0x40,  # 7
                0xF0, 0x90, 0xF0, 0x90, 0xF0,  # 8
                0xF0, 0x90, 0xF0, 0x10, 0xF0,  # 9
                0xF0, 0x90, 0xF0, 0x90, 0x90,  # A
                0xE0, 0x90, 0xE0, 0x90, 0xE0,  # B
                0xF0, 0x80, 0x80, 0x80, 0xF0,  # C
                0xE0, 0x90, 0x90, 0x90, 0xE0,  # D
                0xF0, 0x80, 0xF0, 0x80, 0xF0,  # E
                0xF0, 0x80, 0xF0, 0x80, 0x80,  # F
                )

        # Load font to memory
        addr = uint16()
        for i in range(80):
            addr.value = i
            self.bus.write(addr, uint8(font[i]))

        self.reset()
        self.opcode = uint16(0x0000)

        # this is temporary
        self.instructions = {
            "0NNN": self._0NNN,  # Call
            "00E0": self._00E0,  # Display
            "00EE": self._00EE,  # Flow
            "1NNN": self._1NNN,  # Flow
            "2NNN": self._2NNN,  # Flow
            "3XNN": self._3XNN,  # Cond
            "4XNN": self._4XNN,  # Cond
            "5XY0": self._5XY0,  # Cond
            "6XNN": self._6XNN,  # Const
            "7XNN": self._7XNN,  # Const
            "8XY0": self._8XY0,  # Assign
            "8XY1": self._8XY1,  # BitOp
            "8XY2": self._8XY2,  # BitOp
            "8XY3": self._8XY3,  # BitOp
            "8XY4": self._8XY4,  # Math
            "8XY5": self._8XY5,  # Math
            "8XY6": self._8XY6,  # BitOp
            "8XY7": self._8XY7,  # Math
            "8XYE": self._8XYE,  # BitOp
            "9XY0": self._9XY0,  # Cond
            "ANNN": self._ANNN,  # MEM
            "BNNN": self._BNNN,  # Flow
            "CXNN": self._CXNN,  # Rand
            "DXYN": self._DXYN,  # Disp
            "EX9E": self._EX9E,  # KeyOp
            "EXA1": self._EXA1,  # KeyOp
            "FX07": self._FX07,  # Timer
            "FX0A": self._FX0A,  # KeyOp
            "FX15": self._FX15,  # Timer
            "FX18": self._FX18,  # Sound
            "FX1E": self._FX1E,  # MEM
            "FX29": self._FX29,  # MEM
            "FX33": self._FX33,  # BCD
            "FX55": self._FX55,  # MEM
            "FX65": self._FX65,  # MEM
        }

    def reset(self):
        ZERO = 0x0

        for i in range(len(self.registers['V'])):
            self.registers['V'][i] = ZERO
        self.registers['I'].value = ZERO
        self.registers['SP'].value = ZERO
        self.registers['PC'].value = self._START_PROGRAM_ADDR.value

        self.stack.clear()
        self.timer["delay"] = ZERO
        self.timer["sound"] = ZERO

    def load_rom(self, rom_path, offset=_START_PROGRAM_ADDR):
        print(f'Loading rom from: "{rom_path}"')
        with open(rom_path, 'rb') as file:
            rom = file.read()

        for i, value in enumerate(rom):
            data = uint8(value)
            if value != data.value:
                print(f"[ERROR] Invalid data value: {value} {hex(value)}")
                exit()
            self.bus.write(uint16(offset.value + i), data)

    def fetch_opcode(self):
        """ This method load opcode from memory.
        It also move PC two places along"""
        program_counter = self.registers['PC']

        opcode1 = self.bus.read(program_counter).value
        program_counter.value += 1
        opcode2 = self.bus.read(program_counter).value
        program_counter.value += 1

        self.opcode.value = opcode1 << 8 | opcode2
        print(self.opcode)

    def cycle(self):
        self.fetch_opcode()

        if self.timer['delay'] > 0:
            self.timer['delay'] -= 1
        if self.timer['sound'] > 0:
            self.timer['sound'] -= 1
            if self.timer['sound'] == 0:
                # play sound
                pass

    def _0NNN(self):
        pass

    def _00E0(self):
        pass

    def _00EE(self):
        pass

    def _1NNN(self):
        pass

    def _2NNN(self):
        pass

    def _3XNN(self):
        pass

    def _4XNN(self):
        pass

    def _5XY0(self):
        pass

    def _6XNN(self):
        pass

    def _7XNN(self):
        pass

    def _8XY0(self):
        pass

    def _8XY1(self):
        pass

    def _8XY2(self):
        pass

    def _8XY3(self):
        pass

    def _8XY4(self):
        pass

    def _8XY5(self):
        pass

    def _8XY6(self):
        pass

    def _8XY7(self):
        pass

    def _8XYE(self):
        pass

    def _9XY0(self):
        pass

    def _ANNN(self):
        pass

    def _BNNN(self):
        pass

    def _CXNN(self):
        pass

    def _DXYN(self):
        pass

    def _EX9E(self):
        pass

    def _EXA1(self):
        pass

    def _FX07(self):
        pass

    def _FX0A(self):
        pass

    def _FX15(self):
        pass

    def _FX18(self):
        pass

    def _FX1E(self):
        pass

    def _FX29(self):
        pass

    def _FX33(self):
        pass

    def _FX55(self):
        pass

    def _FX65(self):
        pass


if __name__ == "__main__":
    a = CPU()
    a.load_rom("games\\GUESS")
    a.cycle()

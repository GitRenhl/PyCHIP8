from ctypes import c_uint8 as uint8, \
    c_uint16 as uint16, \
    c_bool

from bus import Bus
import random


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


class Opcode:
    def __init__(self, value):
        self._opcode = uint16(value)

    @property
    def value(self):
        return self._opcode.value

    @value.setter
    def value(self, value):
        self._opcode.value = value

    @property
    def p(self):
        return self._opcode.value >> 12

    @property
    def Vx(self):
        return (self._opcode.value & 0x0f00) >> 8

    @property
    def Vy(self):
        return (self._opcode.value & 0x00f0) >> 4

    @property
    def n(self):
        return self._opcode.value & 0x000f

    @property
    def kk(self):
        return self._opcode.value & 0x00ff

    @property
    def nnn(self):
        return self._opcode.value & 0x0fff


class CPU:
    __slots__ = (
        "bus",
        "registers",
        "key_input",
        "screen",
        "stack",
        "timer",
        "opcode",
        "_value_Vx",
        "_value_Vy",
        "_operators",
        "_logical",
        "_instructions",
    )
    _START_PROGRAM_ADDR = uint16(0x200)
    _ETI_PROGRAM_ADDR = uint16(0x600)
    _END_RAM_ADDR = uint16(0xFFF)
    _SCREEN_SIZE = (64, 32)

    class Error:
        class UnknownOpcodeException(Exception):
            def __init__(self, opcode):
                Exception.__init__(self, f"Unknown opcode: {opcode}")

    def __init__(self):
        """
        REGISTERS:
        [16 x 8-bit] (V0-F) - general purpose registers
        [1 x 16-bit] (I) - index register
        [1 x 16-bit] (SP) - stack pointer
        [1 x 16-bit] (PC) - program counter
        """
        self.bus = Bus(0x1000, self)

        self.registers = {
            'V': (uint8 * 16)(),
            'I': uint16(0x0000),
            'SP': uint16(0x0000),
            'PC': uint16(0x0000),
        }

        # TODO: use uint16 insted of (bool * 16) and save key state as single bite
        self.key_input = (c_bool * 16)()

        # TODO: Change [0] to uint8 or char
        self.screen = [0] * self._SCREEN_SIZE[0] * self._SCREEN_SIZE[1]

        # TODO: Change to uint8 * 12 (or 16)
        self.stack = []
        self.timer = {
            "delay": uint8(),
            "sound": uint8()
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
        self.opcode = Opcode(0x0000)
        self._value_Vx = self.registers['V'][self.opcode.Vx]
        self._value_Vy = self.registers['V'][self.opcode.Vy]

        self._operators = {
            0x0: self._0NNN,             # SYS  nnn
            0x1: self._1NNN,             # JUMP nnn
            0x2: self._2NNN,             # CALL nnn
            0x3: self._3XNN,             # SKE  Vx nn
            0x4: self._4XNN,             # SKNE Vx nn
            0x5: self._5XY0,             # SKE  Vx Vy
            0x6: self._6XNN,             # LOAD Vx nn
            0x7: self._7XNN,             # ADD  Vx nn
            0x8: self._execute_logical,  # Logical
            0x9: self._9XY0,             # SKNE Vx Vy
            0xA: self._ANNN,             # LOAD I nnn
            0xB: self._BNNN,             # JUMP [I] + nnn
            0xC: self._CXNN,             # RAND Vy nn
            0xD: self._DXYN,             # DRAW Vx Vy n
            0xE: self._keyboard,         # Keyboard
            0xF: self._other,            # Other
        }

        self._logical = {
            0x0: self._8XY0,  # LOAD Vx Vy
            0x1: self._8XY1,  # OR   Vx Vy
            0x2: self._8XY2,  # AND  Vx Vy
            0x3: self._8XY3,  # XOR  Vx Vy
            0x4: self._8XY4,  # ADD  Vx Vy
            0x5: self._8XY5,  # SUB  Vx Vy
            0x6: self._8XY6,  # SHR  Vx Vy
            0x7: self._8XY7,  # SUBN Vx Vy
            0xE: self._8XYE,  # SHL  Vx Vy
        }

        # this is temporary
        self._instructions = {
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
        self.timer["delay"].value = ZERO
        self.timer["sound"].value = ZERO

    def load_rom(self, rom_path, offset=_START_PROGRAM_ADDR):
        print(f'Loading rom from: "{rom_path}"')
        if rom_path[-4:] != ".ch8":
            print("[Error] Invalid file type")
            return False
        try:
            with open(rom_path, 'rb') as file:
                rom = file.read()
        except Exception as e:
            print(e)
            return False

        for i, value in enumerate(rom):
            data = uint8(value)
            if value != data.value:
                print(f"[ERROR] Invalid data value: {value} {hex(value)}")
                return False
            self.bus.write(uint16(offset.value + i), data)

        return True

    def _fetch_opcode(self):
        """ This method load opcode from memory.
        It also move PC two places along"""
        program_counter = self.registers['PC']

        opcode1 = self.bus.read(program_counter).value
        program_counter.value += 1
        opcode2 = self.bus.read(program_counter).value
        program_counter.value += 1

        self.opcode.value = opcode1 << 8 | opcode2
        self._value_Vx = self.registers['V'][self.opcode.Vx]
        self._value_Vy = self.registers['V'][self.opcode.Vy]

    def _execute_ins(self):
        self._operators[self.opcode.p]()

    def cycle(self):
        self._fetch_opcode()
        self._execute_ins()

        if self.timer['delay'].value > 0:
            self.timer['delay'].value -= 1
        if self.timer['sound'].value > 0:
            self.timer['sound'].value -= 1
            if self.timer['sound'].value == 0:
                # play sound
                pass

    def _execute_logical(self):
        method = self._logical.get(self.opcode.n)
        if method is None:
            raise self.Error.UnknownOpcodeException(hex(self.opcode.value))

        method()

    def _keyboard(self):
        pass

    def _other(self):
        pass

    def _0NNN(self):
        if self.opcode.kk == 0x00e0:
            self._00E0()
        elif self.opcode.kk == 0x00ee:
            self._00EE()
        else:
            raise self.Error.UnknownOpcodeException(hex(self.opcode.value))

    def _00E0(self):
        self.screen.clear()
        self.screen.append(0)
        self.screen *= self._SCREEN_SIZE[0] * self._SCREEN_SIZE[1]

    def _00EE(self):
        self.registers['PC'].value = self.stack.pop()

    def _1NNN(self):
        self.registers['PC'].value = self.opcode.nnn

    def _2NNN(self):
        self.stack.append(self.registers['PC'].value)
        self.registers['PC'].value = self.opcode.nnn

    def _3XNN(self):
        # Skips the next instruction if VX equals NN
        if self._value_Vx == self.opcode.kk:
            self.registers['PC'].value += 2

    def _4XNN(self):
        # Skips the next instruction if VX doesn't equals NN
        if self._value_Vx != self.opcode.kk:
            self.registers['PC'].value += 2

    def _5XY0(self):
        # Skips the next instruction if VX equals VY
        if self._value_Vx == self._value_Vy:
            self.registers['PC'].value += 2

    def _6XNN(self):
        # Sets VX to NN
        self.registers['V'][self.opcode.Vx] = self.opcode.kk

    def _7XNN(self):
        # Adds VX to NN (Carry flag is not changed)
        self.registers['V'][self.opcode.Vx] += self.opcode.kk

    def _8XY0(self):
        # Sets VX to the value of VY
        regV = self.registers['V']
        regV[self.opcode.Vx] = self._value_Vy

    def _8XY1(self):
        # Sets VX to VX or VY
        regV = self.registers['V']
        regV[self.opcode.Vx] |= self._value_Vy

    def _8XY2(self):
        # Sets VX to VX and VY
        regV = self.registers['V']
        regV[self.opcode.Vx] &= self._value_Vy

    def _8XY3(self):
        # Sets VX to VX xor VY
        regV = self.registers['V']
        regV[self.opcode.Vx] ^= self._value_Vy

    def _8XY4(self):
        # Adds VY to VX. VF is set to 1 when there's a carry, and to 0 when there isn't
        regV = self.registers['V']
        if self._value_Vx + self._value_Vy > 0xff:
            regV[0xf] = 1
        else:
            regV[0xf] = 0
        regV[self.opcode.Vx] += self._value_Vy

    def _8XY5(self):
        # VY is subtracted from VX. VF is set to 0 when there's a borrow, and 1 when there isn't
        regV = self.registers['V']
        if self._value_Vx < self._value_Vy:
            regV[0xf] = 1
        else:
            regV[0xf] = 0
        regV[self.opcode.Vx] -= self._value_Vy

    def _8XY6(self):
        # Stores the least significant bit of VX in VF and then shifts VX to the right by 1
        regV = self.registers['V']
        regV[0xf] = self._value_Vx & 0x0001
        regV[self.opcode.Vx] >>= 1

    def _8XY7(self):
        # Sets VX to VY minus VX. VF is set to 0 when there's a borrow, and 1 when there isn't
        regV = self.registers['V']
        if self._value_Vx > self._value_Vy:
            regV[0xf] = 1
        else:
            regV[0xf] = 0

        regV[self.opcode.Vx] = self._value_Vy - self._value_Vx

    def _8XYE(self):
        # Stores the most significant bit of VX in VF and then shifts VX to the left by 1
        regV = self.registers['V']
        regV[0xf] = self._value_Vx >> 7
        regV[self.opcode.Vx] <<= 1

    def _9XY0(self):
        # Skips the next instruction if VX doesn't equal VY
        # Usually the next instruction is a jump to skip a code block
        if self._value_Vx != self._value_Vy:
            self.registers['PC'] += 2

    def _ANNN(self):
        # Sets I to the address NNN
        self.registers['I'].value = self.opcode.nnn

    def _BNNN(self):
        # Jumps to the address NNN plus V0
        self.registers['PC'] = self.opcode.nnn + self.registers['V'][0x0]

    def _CXNN(self):
        # Sets VX to the result of a bitwise and operation on a random number and NN
        r_num = random.randint(0, 255)
        regV = self.registers['V']
        regV[self.opcode.Vx] = r_num + self.opcode.kk

    def _DXYN(self):
        pass

    def _EX9E(self):
        pass

    def _EXA1(self):
        pass

    def _FX07(self):
        # Sets VX to the value of the delay timer
        regV = self.registers['V']
        regV[self.opcode.Vx] = self.timer['delay'].value

    def _FX0A(self):
        pass

    def _FX15(self):
        # Sets the delay timer to VX
        self.timer['delay'].value = self._value_Vx

    def _FX18(self):
        # Sets the sound timer to VX
        self.timer['sound'].value = self._value_Vx

    def _FX1E(self):
        # Adds VX to I
        regI = self.registers['I']
        if regI.value + self._value_Vx > 0x0fff:
            self.registers['V'][0xf] = 1
        else:
            self.registers['V'][0xf] = 0
        regI.value = (regI.value + self._value_Vx) & 0x0fff

    def _FX29(self):
        # Sets I to the location of the sprite for the character in VX
        self.registers['I'].value = (self._value_Vx * 5)

    def _FX33(self):
        # Stores the BCD decimal representation of VX,
        #  with the most significant of three digits at the address in I,
        #  the middle digit at I plus 1,
        #  the least significant digit at I plus 2
        regI = self.registers['I']
        regI.value = self._value_Vx // 100 << 8
        regI.value += self._value_Vx % 100 // 10 << 4
        regI.value += self._value_Vx % 10

    def _FX55(self):
        # Stores V0 to VX (including VX) in memory starting at address I
        size = self._value_Vx + 1
        regV = self.registers['V']
        regI = self.registers['I']

        for index in range(size):
            address = uint16(regI.value + index)
            self.bus.write(address, regV[index])

        regI.value += size  # Should I remove it?

    def _FX65(self):
        # Fills V0 to VX (including VX) with values from memory starting at address I
        size = self._value_Vx + 1
        regV = self.registers['V']
        regI = self.registers['I']

        for index in range(size):
            regV[index] = regI.value + index

        regI.value += size  # Should I remove it?

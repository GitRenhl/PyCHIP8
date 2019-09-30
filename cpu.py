from ctypes import c_uint8 as uint8, \
    c_uint16 as uint16, \
    c_bool

from bus import Bus
import random
import logging
# import time

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(module)s|%(name)s: %(message)s",
    # handlers=[
    #     logging.FileHandler(
    #         "logs/log_{0.tm_year}{0.tm_mon}{0.tm_mday}.log".format(
    #             time.localtime())
    #     ),
    #     logging.StreamHandler()
    # ]
)
LOG = logging.getLogger('CPU')

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
        "_other",
        "is_drawing"
    )
    _START_PROGRAM_ADDR = uint16(0x200)
    _ETI_PROGRAM_ADDR = uint16(0x600)
    _END_RAM_ADDR = uint16(0xFFF)
    _SCREEN_SIZE = (64, 32)

    class Error:
        class UnknownOpcodeException(Exception):
            def __init__(self, opcode):
                Exception.__init__(self, f"Unknown opcode: {opcode}")
    KEY_MAP = {
        0x0: 0b0010000000000000,
        0x1: 0b0000000000000001,
        0x2: 0b0000000000000010,
        0x3: 0b0000000000000100,
        0x4: 0b0000000000010000,
        0x5: 0b0000000000100000,
        0x6: 0b0000000001000000,
        0x7: 0b0000000100000000,
        0x8: 0b0000001000000000,
        0x9: 0b0000010000000000,
        0xa: 0b0001000000000000,
        0xb: 0b0100000000000000,
        0xc: 0b0000000000001000,
        0xd: 0b0000000010000000,
        0xe: 0b0000100000000000,
        0xf: 0b1000000000000000
    }

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

        self.key_input = uint16()

        self.screen = (uint8 * (self._SCREEN_SIZE[0] * self._SCREEN_SIZE[1]))()

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

        self.is_drawing = False
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
            0xF: self._other_inst,       # Other
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
        self._other = {
            0x07: self._FX07,  # LOAD Vx DELAY
            0x0A: self._FX0A,  # LD Vx KEY
            0x15: self._FX15,  # LOAD DT Vx
            0x18: self._FX18,  # LOAD ST Vx
            0x1E: self._FX1E,  # ADD  I Vx
            0x29: self._FX29,  # LOAD I Vx
            0x33: self._FX33,  # LD BCD Vx
            0x55: self._FX55,  # STOR [I] Vx
            0x65: self._FX65,  # LOAD Vx [I]
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
        self.clear_display()

    def load_rom(self, rom_path, offset=_START_PROGRAM_ADDR):
        LOG.info(f'Loading rom from: "{rom_path}"')
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

    def _other_inst(self):
        method = self._other.get(self.opcode.kk)
        if method is None:
            raise self.Error.UnknownOpcodeException(hex(self.opcode.value))

        method()

    def is_key_pressed(self, key):
        if key > 0xf:
            return False
        else:
            return self.key_input.value & self.KEY_MAP.get(key) != 0

    def press_key(self, key):
        if self.is_key_pressed(key):
            return
        self.key_input.value ^= self.KEY_MAP.get(key, 0)

    def release_key(self, key):
        if not self.is_key_pressed(key):
            return
        self.key_input.value ^= self.KEY_MAP.get(key, 0)

    def clear_display(self):
        LOG.debug("Clear the display")
        for i in range(len(self.screen)):
            self.screen[i] = 0x00
        self.is_drawing = True

    def _0NNN(self):
        if self.opcode.kk == 0x00e0:
            self._00E0()
        elif self.opcode.kk == 0x00ee:
            self._00EE()
        else:
            raise self.Error.UnknownOpcodeException(hex(self.opcode.value))

    def _00E0(self):
        # Clear the display
        LOG.debug("CLS")
        self.clear_display()

    def _00EE(self):
        # Returns from a subroutine
        LOG.debug("[00EE] RET")
        self.registers['PC'].value = self.stack.pop()

    def _1NNN(self):
        # Jumps to address NNN
        LOG.debug(f"[1NNN] JP NNN({self.opcode.nnn})")
        self.registers['PC'].value = self.opcode.nnn

    def _2NNN(self):
        # Calls subroutine at NNN
        LOG.debug(f"[2NNN] CALL NNN({self.opcode.nnn})")
        self.stack.append(self.registers['PC'].value)
        self.registers['PC'].value = self.opcode.nnn

    def _3XNN(self):
        # Skips the next instruction if VX equals NN
        LOG.debug(f"[3XNN] SE Vx({self.opcode.Vx}, {self._value_Vx}), NN({self.opcode.kk})")
        if self._value_Vx == self.opcode.kk:
            self.registers['PC'].value += 2

    def _4XNN(self):
        # Skips the next instruction if VX doesn't equals NN
        LOG.debug(f"[4XNN] SNE Vx({self.opcode.Vx}, {self._value_Vx}), NN({self.opcode.kk})")
        if self._value_Vx != self.opcode.kk:
            self.registers['PC'].value += 2

    def _5XY0(self):
        # Skips the next instruction if VX equals VY
        LOG.debug(f"[5XY0] SE Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        if self._value_Vx == self._value_Vy:
            self.registers['PC'].value += 2

    def _6XNN(self):
        # Sets VX to NN
        LOG.debug(f"[4XNN] LD Vx({self.opcode.Vx}, {self._value_Vx}), NN({self.opcode.kk})")
        self.registers['V'][self.opcode.Vx] = self.opcode.kk

    def _7XNN(self):
        # Adds VX to NN (Carry flag is not changed)
        LOG.debug(f"[7XNN] ADD Vx({self.opcode.Vx}, {self._value_Vx}), NN({self.opcode.kk})")
        self.registers['V'][self.opcode.Vx] += self.opcode.kk

    def _8XY0(self):
        # Sets VX to the value of VY
        LOG.debug(f"[8XY1] LD Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        regV = self.registers['V']
        regV[self.opcode.Vx] = self._value_Vy

    def _8XY1(self):
        # Sets VX to VX or VY
        LOG.debug(f"[8XY1] OR Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        regV = self.registers['V']
        regV[self.opcode.Vx] |= self._value_Vy

    def _8XY2(self):
        # Sets VX to VX and VY
        LOG.debug(f"[8XY2] AND Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        regV = self.registers['V']
        regV[self.opcode.Vx] &= self._value_Vy

    def _8XY3(self):
        # Sets VX to VX xor VY
        LOG.debug(f"[8XY3] XOR Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        regV = self.registers['V']
        regV[self.opcode.Vx] ^= self._value_Vy

    def _8XY4(self):
        # Adds VY to VX. VF is set to 1 when there's a carry,
        #  and to 0 when there isn't
        LOG.debug(f"[8XY4] ADD Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        regV = self.registers['V']
        if self._value_Vx + self._value_Vy > 0xff:
            regV[0xf] = 1
        else:
            regV[0xf] = 0
        regV[self.opcode.Vx] += self._value_Vy

    def _8XY5(self):
        # VY is subtracted from VX.
        # VF is set to 0 when there's a borrow,
        #  and 1 when there isn't
        LOG.debug(f"[8XY5] SUB Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        regV = self.registers['V']
        if self._value_Vx > self._value_Vy:
            regV[0xf] = 1
        else:
            regV[0xf] = 0
        regV[self.opcode.Vx] -= self._value_Vy

    def _8XY6(self):
        # Stores the least significant bit of VX in VF
        #  and then shifts VX to the right by 1
        LOG.debug(f"[8XY6] SHR Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        regV = self.registers['V']
        regV[0xf] = self._value_Vx & 0x0001
        regV[self.opcode.Vx] >>= 1

    def _8XY7(self):
        # Sets VX to VY minus VX.
        # VF is set to 0 when there's a borrow,
        #  and 1 when there isn't
        LOG.debug(f"[8XY7] SUBN Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        regV = self.registers['V']
        if self._value_Vy > self._value_Vx:
            regV[0xf] = 1
        else:
            regV[0xf] = 0

        regV[self.opcode.Vx] = self._value_Vy - self._value_Vx

    def _8XYE(self):
        # Stores the most significant bit of VX in VF
        #  and then shifts VX to the left by 1
        LOG.debug(f"[8XYE] SHL Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        regV = self.registers['V']
        regV[0xf] = self._value_Vx >> 7
        regV[self.opcode.Vx] <<= 1

    def _9XY0(self):
        # Skips the next instruction if VX doesn't equal VY.
        # Usually the next instruction is a jump to skip a code block
        LOG.debug(f"[9XY0] SKNE Vx({self.opcode.Vx}, {self._value_Vx}), VY({self.opcode.Vy}, {self._value_Vy})")
        if self._value_Vx != self._value_Vy:
            self.registers['PC'].value += 2

    def _ANNN(self):
        # Sets I to the address NNN
        LOG.debug(f"[ANNN] LOAD I[{self.registers['I'].value}] nnn[{self.opcode.nnn}]")
        self.registers['I'].value = self.opcode.nnn

    def _BNNN(self):
        # Jumps to the address NNN plus V0
        LOG.debug(f"[BNNN] JP V0({self.registers['V'][0x0]}), addr({self.opcode.nnn})")
        self.registers['PC'].value = self.opcode.nnn + self.registers['V'][0x0]

    def _CXNN(self):
        # Sets VX to the result of a bitwise and operation
        #  on a random number and NN
        LOG.debug(f"[CXNN] RAND Vx nn[{self.opcode.kk}]")
        r_num = random.randint(0, 255)
        regV = self.registers['V']
        regV[self.opcode.Vx] = r_num & self.opcode.kk

    def _DXYN(self):
        # Display n-byte sprite starting at memory location I
        #  at (Vx, Vy), set VF = collision
        LOG.debug(f"[DXYN] DRAW Vx({self.opcode.Vx}, {self._value_Vx}) Vy({self.opcode.Vy}, {self._value_Vy}) nibble({self.opcode.n})")

        self.registers['V'][0xf] = 0
        pos = self._value_Vx, self._value_Vy
        n_bytes = self.opcode.n  # height
        regI = self.registers['I']

        for y_offset in range(n_bytes):
            row = self.bus.read(uint16(regI.value + y_offset)).value
            for x_offset in range(8):
                x = pos[0] + x_offset-1
                y = pos[1] + y_offset
                if x >= self._SCREEN_SIZE[0] or y >= self._SCREEN_SIZE[1]:
                    continue

                location = y * self._SCREEN_SIZE[0] + x
                mask = 1 << 8 - x_offset
                curr_pixel = (row & mask) >> (8 - x_offset)
                try:
                    self.screen[location] ^= curr_pixel
                except IndexError as e:
                    print(e, location, curr_pixel, self.opcode.value)
                # print(location, curr_pixel)
                if self.screen[location] == 0:
                    self.registers['V'][0xf] = 1
                else:
                    self.registers['V'][0xf] = 0
        self.is_drawing = True

    def _EX9E(self):
        # Skips the next instruction if the key stored in VX is pressed.
        LOG.debug(f"[EX9E] SKPR Vx({self.opcode.Vx}, {self._value_Vx})")
        if self.is_key_pressed(self._value_Vx):
            self.registers['PC'].value += 2

    def _EXA1(self):
        # Skips the next instruction if the key stored in VX isn't pressed.
        LOG.debug(f"[EXA1] SKUP Vx({self.opcode.Vx}, {self._value_Vx})")
        if not self.is_key_pressed(self._value_Vx):
            self.registers['PC'].value += 2

    def _FX07(self):
        # Sets VX to the value of the delay timer
        LOG.debug(f"[FX07] LOAD Vx[{self.opcode.Vx}, {self._value_Vx}] DELAY[{self.timer['delay'].value}]")
        regV = self.registers['V']
        regV[self.opcode.Vx] = self.timer['delay'].value

    def _FX0A(self):
        # A key press is awaited, and then stored in VX
        LOG.debug(f"[FX0A] LD Vx[{self.opcode.Vx}, {self._value_Vx}] KEY")
        if self.key_input.value > 0:
            for key in self.KEY_MAP:
                if self.is_key_pressed(key):
                    return key
        else:
            self.registers['PC'].value -= 2

    def _FX15(self):
        # Sets the delay timer to VX
        LOG.debug(f"[FX16] LOAD DT Vx[{self.opcode.Vx}, {self._value_Vx}]")
        self.timer['delay'].value = self._value_Vx

    def _FX18(self):
        # Sets the sound timer to VX
        LOG.debug(f"[FX18] LOAD ST Vx[{self.opcode.Vx}, {self._value_Vx}]")
        self.timer['sound'].value = self._value_Vx

    def _FX1E(self):
        # Adds VX to I
        LOG.debug(f"[FX1E] ADD  I[{self.registers['I'].value}] Vx[{self.opcode.Vx}, {self._value_Vx}]")
        regI = self.registers['I']
        if regI.value + self._value_Vx > 0x0fff:
            self.registers['V'][0xf] = 1
        else:
            self.registers['V'][0xf] = 0
        regI.value = (regI.value + self._value_Vx) & 0x0fff

    def _FX29(self):
        # Sets I to the location of the sprite for the character in VX
        LOG.debug(f"[FX29] LOAD I[{self.registers['I'].value}] Vx[{self.opcode.Vx}, {self._value_Vx}]")
        self.registers['I'].value = self._value_Vx * 5

    def _FX33(self):
        # Stores the BCD decimal representation of VX,
        #  with the most significant of three digits at the address in I,
        #  the middle digit at I plus 1,
        #  the least significant digit at I plus 2
        LOG.debug(f"[FX33] LD BCD Vx[{self.opcode.Vx}, {self._value_Vx}]")
        address = uint16(self.registers['I'].value)
        self.bus.write(address, uint8(self._value_Vx // 100))
        address.value += 1
        self.bus.write(address, uint8(self._value_Vx % 100 // 10))
        address.value += 1
        self.bus.write(address, uint8(self._value_Vx % 10))

    def _FX55(self):
        # Stores V0 to VX (including VX) in memory starting at address I
        LOG.debug(f"[FX55] STOR [I][{self.registers['I'].value}] Vx[{self.opcode.Vx}, {self._value_Vx}]")
        size = self.opcode.Vx + 1
        regV = self.registers['V']
        regI = self.registers['I']

        for index in range(size):
            self.bus.write(regI, uint8(regV[index]))
            regI.value += 1

    def _FX65(self):
        # Fills V0 to VX (including VX) with values
        #  from memory starting at address I
        LOG.debug(f"[FX65] LOAD Vx[{self.opcode.Vx}, {self._value_Vx}] [I][{self.registers['I'].value}]")
        size = self.opcode.Vx + 1
        regV = self.registers['V']
        regI = self.registers['I']

        for index in range(size):
            regV[index] = self.bus.read(regI)
            regI.value += 1

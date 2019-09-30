import pyxel
from ctypes import c_uint16
from cpu import CPU


class App:
    HEX_PROMPT = "0x"

    # Position drawable objects
    POS_SCREEN = (0, 0)
    POS_OPCODE = (2, 34)
    POS_REGISTER_V = (2, 50)
    POS_REGISTER_ISP_TIMER = (2, 103)
    POS_KEY_STATUS = (66, 2)
    POS_CYCLE_COUNT = (66, 22)
    POS_MEM = (66, 53)
    MEM_LINES = 12

    # COLORS
    TEXT_COLOR = pyxel.COLOR_WHITE
    TEXT_COLOR_OTHER = pyxel.COLOR_LIGHTGRAY

    # KEYBOARD
    KEY_MAP = {
        pyxel.KEY_1: 0x1, pyxel.KEY_2: 0x2, pyxel.KEY_3: 0x3, pyxel.KEY_4: 0xc,
        pyxel.KEY_Q: 0x4, pyxel.KEY_W: 0x5, pyxel.KEY_E: 0x6, pyxel.KEY_R: 0xd,
        pyxel.KEY_A: 0x7, pyxel.KEY_S: 0x8, pyxel.KEY_D: 0x9, pyxel.KEY_F: 0xe,
        pyxel.KEY_Z: 0xa, pyxel.KEY_X: 0x0, pyxel.KEY_C: 0xb, pyxel.KEY_V: 0xf
    }

    def __init__(self):
        self._is_running = False
        pyxel.init(128, 128, fps=30)
        pyxel.mouse(False)
        pyxel.load("assets\\asset.pyxres")

        self.cpu = CPU()
        valid = self.cpu.load_rom("games\\BLITZ.ch8")
        if not valid:
            exit()

        self._clock_counter = 0

        # References
        self._registers = self.cpu.registers
        self._timer = self.cpu.timer
        self._opcode = self.cpu.opcode
        self._current_pc = self.cpu.registers["PC"].value
        self._next_pc = self.cpu.registers["PC"].value + 2

    def run(self):
        if self._is_running:
            return
        self._is_running = True
        pyxel.run(self.update, self.draw)

    @property
    def is_running(self):
        return self._is_running

    def change_int_to_hexstr(self, number, size):
        text = hex(number)[2:]
        text = self.HEX_PROMPT + "0" * (size - len(text)) + text
        return text

    def _draw_screen(self):
        if not self.cpu.is_drawing:
            return

        self.cpu.is_drawing = False

        x, y = self.POS_SCREEN
        w, _ = self.cpu._SCREEN_SIZE
        # pyxel.rectb(x - 1, y - 1, w + 2, h + 2, 13)  # Border
        for i, color in enumerate(self.cpu.screen):
            pix_y = i // w
            pix_x = i % w
            pyxel.pix(pix_x + x, pix_y + y, color * 7)

    def _draw_rV(self):
        Vreg = self._registers['V']
        name_x, y = self.POS_REGISTER_V
        value_x = name_x + 2 * pyxel.FONT_WIDTH + 2
        for i, value in enumerate(Vreg):
            vaddr = hex(i)[2:].upper()

            text = self.change_int_to_hexstr(value, 2)
            pyxel.text(name_x, y, f"V{vaddr}", self.TEXT_COLOR_OTHER)
            pyxel.text(value_x, y, text, self.TEXT_COLOR)
            if i == 7:
                name_x += 34
                value_x += 34
                y = self.POS_REGISTER_V[1]
            else:
                y += pyxel.FONT_HEIGHT

    def _draw_opcode_and_rPC(self):
        NAME_X, y = self.POS_OPCODE
        VALUE_X = NAME_X + 8 * pyxel.FONT_WIDTH
        text = self.change_int_to_hexstr(self._current_pc, 4)
        pyxel.text(NAME_X, y, "CURR PC", self.TEXT_COLOR_OTHER)
        pyxel.text(VALUE_X, y, text, self.TEXT_COLOR)

        text = self.change_int_to_hexstr(self._next_pc, 4)
        pyxel.text(NAME_X + 62, y, "NEXT PC", self.TEXT_COLOR_OTHER)
        pyxel.text(VALUE_X + 62, y, text, self.TEXT_COLOR)

        y += pyxel.FONT_HEIGHT + 1
        text = self.change_int_to_hexstr(self._opcode.value, 4)
        pyxel.text(NAME_X, y, "OPCODE", self.TEXT_COLOR_OTHER)
        pyxel.text(VALUE_X, y, text, self.TEXT_COLOR)

    def _draw_rI_rSP_timers(self):
        NAME_X, y = self.POS_REGISTER_ISP_TIMER
        VALUE_X = NAME_X + 5 * pyxel.FONT_WIDTH + 2
        text = self.change_int_to_hexstr(self._registers['I'].value, 4)
        pyxel.text(NAME_X, y, "R[I]", self.TEXT_COLOR_OTHER)
        pyxel.text(VALUE_X, y, text, self.TEXT_COLOR)

        y += pyxel.FONT_HEIGHT
        text = self.change_int_to_hexstr(self._registers['SP'].value, 4)
        pyxel.text(NAME_X, y, "R[SP]", self.TEXT_COLOR_OTHER)
        pyxel.text(VALUE_X, y, text, self.TEXT_COLOR)

        y += pyxel.FONT_HEIGHT
        text = self.change_int_to_hexstr(self._timer['delay'].value, 2)
        pyxel.text(NAME_X, y, "DT", self.TEXT_COLOR_OTHER)
        pyxel.text(VALUE_X, y, text, self.TEXT_COLOR)

        y += pyxel.FONT_HEIGHT
        text = self.change_int_to_hexstr(self._timer['sound'].value, 2)
        pyxel.text(NAME_X, y, "ST", self.TEXT_COLOR_OTHER)
        pyxel.text(VALUE_X, y, text, self.TEXT_COLOR)

    def _draw_key_status(self):
        x, y = self.POS_KEY_STATUS
        pyxel.text(x, y, "KEYBOARD:", self.TEXT_COLOR)
        x += 9 * pyxel.FONT_WIDTH
        key_state = self.cpu.key_input
        text = ""
        for i in range(0, 16, 4):
            byte = 2 ** i
            text += str(int(key_state.value & byte > 0))
            byte *= 2
            text += str(int(key_state.value & byte > 0))
            byte *= 2
            text += str(int(key_state.value & byte > 0))
            byte *= 2
            text += str(int(key_state.value & byte > 0))
            text += "\n"

        pyxel.text(x, y, text, self.TEXT_COLOR)

    def _draw_mem(self):
        ADDR_X, y = self.POS_MEM
        VALUE_X = ADDR_X + 7 * pyxel.FONT_WIDTH
        PC = self._current_pc - self.MEM_LINES // 2

        adresses_str = ""
        values_str = ""
        for i in range(self.MEM_LINES):
            address = PC + i*2

            value1 = self.cpu.bus.read(c_uint16(address)).value
            value2 = self.cpu.bus.read(c_uint16(address + 1)).value
            value1 = self.change_int_to_hexstr(value1, 2)[2:]
            value2 = self.change_int_to_hexstr(value2, 2)[2:]

            adresses_str = self.change_int_to_hexstr(address, 4)
            values_str = f"{value1} {value2}"

            if address == self._current_pc:
                pyxel.text(ADDR_X, y, adresses_str, 11)
            else:
                pyxel.text(ADDR_X, y, adresses_str, self.TEXT_COLOR_OTHER)
            pyxel.text(VALUE_X, y, values_str, self.TEXT_COLOR)
            y += pyxel.FONT_HEIGHT

    def do_cycle(self):
        self._current_pc = self.cpu.registers["PC"].value
        self.cpu.cycle()
        self._clock_counter += 1
        self._next_pc = self.cpu.registers["PC"].value

    def update(self):
        if pyxel.btnp(pyxel.KEY_F1):
            self.cpu.reset()
            self._clock_counter = 0
            print("SOFT RESET")
            return

        for key, key_m in self.KEY_MAP.items():
            if pyxel.btnp(key):
                self.cpu.press_key(key_m)
            elif pyxel.btnr(key):
                self.cpu.release_key(key_m)

        if pyxel.btnp(pyxel.KEY_SPACE, 10, 1):
            self.do_cycle()

    def draw(self):
        # pyxel.cls(0)
        self._draw_screen()

        pyxel.bltm(0, 0, 0, 0, 0, 16, 16, 0)

        self._draw_opcode_and_rPC()
        self._draw_rV()
        self._draw_rI_rSP_timers()
        self._draw_key_status()
        self._draw_mem()

        x, y = self.POS_CYCLE_COUNT
        pyxel.text(x, y, str(self._clock_counter), 7)

        # x, y = pyxel.mouse_x, pyxel.mouse_y
        # pyxel.text(2, 2, str((x, y)), 7)


if __name__ == "__main__":
    app = App()
    app.run()

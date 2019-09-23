import random
from ctypes import c_uint8, c_uint16


class Bus:
    __slots__ = ("_cpu", "SIZE", "_ram")

    def __init__(self, size, cpu=None):
        """
        size: max is 0xFFFF
        """
        assert size <= 0xFFFF

        self._cpu = cpu

        self.SIZE = size
        default_value_gen = (0x00 for _ in range(self.SIZE))
        self._ram = (c_uint8 * self.SIZE)(*default_value_gen)

    def _is_address_correct(self, addr: c_uint16) -> bool:
        return addr.value >= 0x0000 and addr.value <= self.SIZE

    # def _clear_ram(self):
    #     for i in range(len(self._ram)):
    #         self._ram[i] = 0x00

    def write(self, addr: c_uint16, data: c_uint8) -> None:
        if self._is_address_correct(addr):
            try:
                self._ram[addr.value] = data.value
            except IndexError as e:
                print("WRITE ERROR:", e, addr, data)
                exit()

    def read(self, addr: c_uint16) -> c_uint8:
        data = c_uint8(0x00)
        if self._is_address_correct(addr):
            try:
                data.value = self._ram[addr.value]
            except IndexError as e:
                print(f"{e}: {addr}")
                exit()

        return data

    def display(self, start_addr, lines, length=8):
        assert start_addr >= 0x0000
        assert length > 1
        assert length % 2 == 0

        print(f"RAM size: {len(self._ram)}")
        top = "address|"
        margin = "-------|"
        for i in range(0, length, 2):
            j1 = hex(i)[2:]
            j2 = hex(i + 1)[2:]
            top += f" {j1 if i > 15 else '0' + j1} {j2 if i > 15 else '0' + j2} |"
            margin += "-------|"
        print(top + "\n" + margin)
        del top, margin, j1, j2  # clear

        lines = lines * length
        for i in range(start_addr, start_addr + lines, length):
            data = ""
            for j in range(0, length, 2):
                addr = i + j
                value1 = hex(self.read(c_uint16(addr)).value)[2:]
                value2 = hex(self.read(c_uint16(addr + 1)).value)[2:]
                if len(value1) == 1:
                    value1 = "0" + value1
                if len(value2) == 1:
                    value2 = "0" + value2
                data += f"{value1} {value2} | "

            addr = hex(i)[2:]
            while len(addr) < 4:
                addr = "0"+addr
            text = f"0x{addr} | {data}"
            print(text)
        print()


if __name__ == "__main__":
    bus = Bus(64)
    # for i in range(20):
    #     addr = c_uint16(random.randint(0, 63))
    #     data = c_uint8(random.randint(0, 255))
    #     bus.write(addr, data)
    # print(hex(addr.value), data)
    bus.write(c_uint16(0), c_uint8(0xff))
    bus.write(c_uint16(bus.SIZE-1), c_uint8(0xff))
    length = 4
    bus.display(0, bus.SIZE//length, length)

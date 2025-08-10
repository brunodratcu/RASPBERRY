# ili9XXX.py - Driver MicroPython para controladores ILI9xxx (ILI9488, ILI9341, ST7789)
# Adaptado para Raspberry Pi Pico / Pico W
# Suporte a displays até 480x320
# Autor: Adaptado de russhughes / micropython-ili9341-st7789

from machine import Pin, SPI
import time
import framebuf

def color565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

class ILI9488:
    def __init__(self, spi, cs, dc, rst, width=480, height=320, rot=0):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.width = width
        self.height = height
        self.rotation = rot
        self.buffer = bytearray(self.width * self.height * 2)  # RGB565
        self.framebuf = framebuf.FrameBuffer(self.buffer, self.width, self.height, framebuf.RGB565)
        self.init_pins()
        self.reset()
        self.init_display()

    def init_pins(self):
        self.cs.init(Pin.OUT, value=1)
        self.dc.init(Pin.OUT, value=0)
        self.rst.init(Pin.OUT, value=1)

    def reset(self):
        self.rst(0)
        time.sleep_ms(50)
        self.rst(1)
        time.sleep_ms(150)

    def write_cmd(self, cmd):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def write_data(self, data):
        self.cs(0)
        self.dc(1)
        self.spi.write(bytearray([data]) if isinstance(data, int) else data)
        self.cs(1)

    def init_display(self):
        # Sequência de inicialização para ILI9488
        self.write_cmd(0x01)  # Software reset
        time.sleep_ms(50)

        self.write_cmd(0x3A)  # Pixel format
        self.write_data(0x55)  # 16 bits por pixel

        self.write_cmd(0x36)  # Memory Access Control
        if self.rotation == 0:
            self.write_data(0x48)
        else:
            self.write_data(0x28)

        self.write_cmd(0x11)  # Exit Sleep
        time.sleep_ms(120)

        self.write_cmd(0x29)  # Display ON
        time.sleep_ms(50)

    def fill(self, color):
        self.framebuf.fill(color)
        self.show()

    def pixel(self, x, y, color):
        self.framebuf.pixel(x, y, color)

    def text(self, font, string, x, y, color, background=0x0000):
        for i, char in enumerate(string):
            self.char(font, char, x + i * font.WIDTH, y, color, background)

    def char(self, font, char, x, y, color, background):
        ch = ord(char)
        if ch < 32 or ch > 126:
            ch = 32
        offset = (ch - 32) * font.HEIGHT
        for row in range(font.HEIGHT):
            bits = font.font[offset + row]
            for col in range(font.WIDTH):
                if bits & (1 << (7 - col)):
                    self.framebuf.pixel(x + col, y + row, color)
                else:
                    self.framebuf.pixel(x + col, y + row, background)

    def show(self):
        self.write_cmd(0x2A)  # Col addr set
        self.write_data(self.width >> 8)
        self.write_data(self.width & 0xFF)
        self.write_data((self.width - 1) >> 8)
        self.write_data((self.width - 1) & 0xFF)

        self.write_cmd(0x2B)  # Row addr set
        self.write_data(self.height >> 8)
        self.write_data(self.height & 0xFF)
        self.write_data((self.height - 1) >> 8)
        self.write_data((self.height - 1) & 0xFF)

        self.write_cmd(0x2C)  # RAM write
        self.cs(0)
        self.dc(1)
        self.spi.write(self.buffer)
        self.cs(1)

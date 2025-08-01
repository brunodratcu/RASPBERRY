import utime
import framebuf

class ILI9341:
    def __init__(self, spi, cs, dc, rst, width=240, height=320):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.width = width
        self.height = height

        self.cs.init(self.cs.OUT, value=1)
        self.dc.init(self.dc.OUT, value=0)
        self.rst.init(self.rst.OUT, value=1)

        self.reset()
        self.init_display()
        self.buffer = framebuf.FrameBuffer(bytearray(self.width * self.height * 2), self.width, self.height, framebuf.RGB565)

    def reset(self):
        self.rst.value(1)
        utime.sleep_ms(5)
        self.rst.value(0)
        utime.sleep_ms(20)
        self.rst.value(1)
        utime.sleep_ms(150)

    def write_cmd(self, cmd):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytearray([cmd]))
        self.cs.value(1)

    def write_data(self, data):
        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(bytearray([data]))
        self.cs.value(1)

    def init_display(self):
        self.write_cmd(0x01)  # Software reset
        utime.sleep_ms(150)
        self.write_cmd(0x28)  # Display OFF
        self.write_cmd(0x3A)  # Pixel Format Set
        self.write_data(0x55)  # 16 bits per pixel
        self.write_cmd(0x29)  # Display ON
        utime.sleep_ms(100)

    def fill(self, color):
        color_hi = color >> 8
        color_lo = color & 0xFF
        data = bytearray([color_hi, color_lo] * self.width)
        for y in range(self.height):
            self.set_window(0, y, self.width - 1, y)
            self.dc.value(1)
            self.cs.value(0)
            self.spi.write(data)
            self.cs.value(1)

    def set_window(self, x0, y0, x1, y1):
        self.write_cmd(0x2A)
        self.write_data(x0 >> 8)
        self.write_data(x0 & 0xFF)
        self.write_data(x1 >> 8)
        self.write_data(x1 & 0xFF)
        self.write_cmd(0x2B)
        self.write_data(y0 >> 8)
        self.write_data(y0 & 0xFF)
        self.write_data(y1 >> 8)
        self.write_data(y1 & 0xFF)
        self.write_cmd(0x2C)

    def show(self):
        self.set_window(0, 0, self.width - 1, self.height - 1)
        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(self.buffer)
        self.cs.value(1)

    def text(self, text, x, y, color=0xFFFF):
        self.buffer.text(text, x, y, color)

    def fill_rect(self, x, y, w, h, color):
        self.buffer.fill_rect(x, y, w, h, color)

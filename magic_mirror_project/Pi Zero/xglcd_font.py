import struct

class XglcdFont:
    def __init__(self, path, width, height, start_char=32, num_chars=96, reverse_bytes=False):
        self.path = path
        self.width = width
        self.height = height
        self.start_char = start_char
        self.num_chars = num_chars
        self.reverse_bytes = reverse_bytes
        self.bytes_per_char = (height * width) // 8

        with open(path, 'rb') as f:
            self.font_data = f.read()

    def get_char_bytes(self, char):
        index = (ord(char) - self.start_char) * self.bytes_per_char
        return self.font_data[index:index + self.bytes_per_char]

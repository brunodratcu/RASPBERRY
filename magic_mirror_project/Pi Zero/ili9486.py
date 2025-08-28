# ili9486.py - Biblioteca melhorada para display ILI9486 320x480
import machine
import utime
from machine import Pin, SPI

# Fonte 8x8 básica para números e letras
FONT_8x8 = {
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    '0': [0x3C, 0x66, 0x6E, 0x76, 0x66, 0x66, 0x3C, 0x00],
    '1': [0x18, 0x38, 0x18, 0x18, 0x18, 0x18, 0x7E, 0x00],
    '2': [0x3C, 0x66, 0x06, 0x0C, 0x18, 0x30, 0x7E, 0x00],
    '3': [0x3C, 0x66, 0x06, 0x1C, 0x06, 0x66, 0x3C, 0x00],
    '4': [0x0C, 0x1C, 0x2C, 0x4C, 0x7E, 0x0C, 0x0C, 0x00],
    '5': [0x7E, 0x60, 0x7C, 0x06, 0x06, 0x66, 0x3C, 0x00],
    '6': [0x1C, 0x30, 0x60, 0x7C, 0x66, 0x66, 0x3C, 0x00],
    '7': [0x7E, 0x06, 0x0C, 0x18, 0x30, 0x30, 0x30, 0x00],
    '8': [0x3C, 0x66, 0x66, 0x3C, 0x66, 0x66, 0x3C, 0x00],
    '9': [0x3C, 0x66, 0x66, 0x3E, 0x06, 0x0C, 0x38, 0x00],
    ':': [0x00, 0x18, 0x18, 0x00, 0x18, 0x18, 0x00, 0x00],
    '/': [0x06, 0x0C, 0x18, 0x30, 0x60, 0xC0, 0x80, 0x00],
    'A': [0x3C, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
    'B': [0x7C, 0x66, 0x66, 0x7C, 0x66, 0x66, 0x7C, 0x00],
    'C': [0x3C, 0x66, 0x60, 0x60, 0x60, 0x66, 0x3C, 0x00],
    'D': [0x78, 0x6C, 0x66, 0x66, 0x66, 0x6C, 0x78, 0x00],
    'E': [0x7E, 0x60, 0x60, 0x78, 0x60, 0x60, 0x7E, 0x00],
    'F': [0x7E, 0x60, 0x60, 0x78, 0x60, 0x60, 0x60, 0x00],
    'G': [0x3C, 0x66, 0x60, 0x6E, 0x66, 0x66, 0x3C, 0x00],
    'H': [0x66, 0x66, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00],
    'I': [0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x7E, 0x00],
    'J': [0x3E, 0x0C, 0x0C, 0x0C, 0x0C, 0x6C, 0x38, 0x00],
    'K': [0x66, 0x6C, 0x78, 0x70, 0x78, 0x6C, 0x66, 0x00],
    'L': [0x60, 0x60, 0x60, 0x60, 0x60, 0x60, 0x7E, 0x00],
    'M': [0x63, 0x77, 0x7F, 0x6B, 0x63, 0x63, 0x63, 0x00],
    'N': [0x66, 0x76, 0x7E, 0x7E, 0x6E, 0x66, 0x66, 0x00],
    'O': [0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'P': [0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60, 0x60, 0x00],
    'Q': [0x3C, 0x66, 0x66, 0x66, 0x6A, 0x6C, 0x36, 0x00],
    'R': [0x7C, 0x66, 0x66, 0x7C, 0x6C, 0x66, 0x66, 0x00],
    'S': [0x3C, 0x66, 0x60, 0x3C, 0x06, 0x66, 0x3C, 0x00],
    'T': [0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00],
    'U': [0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'V': [0x66, 0x66, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
    'W': [0x63, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x63, 0x00],
    'X': [0x66, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0x66, 0x00],
    'Y': [0x66, 0x66, 0x66, 0x3C, 0x18, 0x18, 0x18, 0x00],
    'Z': [0x7E, 0x0E, 0x1C, 0x38, 0x70, 0x7E, 0x00, 0x00],
    'a': [0x00, 0x00, 0x3C, 0x06, 0x3E, 0x66, 0x3E, 0x00],
    'b': [0x60, 0x60, 0x7C, 0x66, 0x66, 0x66, 0x7C, 0x00],
    'c': [0x00, 0x00, 0x3C, 0x66, 0x60, 0x66, 0x3C, 0x00],
    'd': [0x06, 0x06, 0x3E, 0x66, 0x66, 0x66, 0x3E, 0x00],
    'e': [0x00, 0x00, 0x3C, 0x66, 0x7E, 0x60, 0x3C, 0x00],
    'f': [0x1C, 0x36, 0x30, 0x7C, 0x30, 0x30, 0x30, 0x00],
    'g': [0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x3C],
    'h': [0x60, 0x60, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x00],
    'i': [0x18, 0x00, 0x38, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'j': [0x06, 0x00, 0x0E, 0x06, 0x06, 0x06, 0x66, 0x3C],
    'k': [0x60, 0x60, 0x66, 0x6C, 0x78, 0x6C, 0x66, 0x00],
    'l': [0x38, 0x18, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    'm': [0x00, 0x00, 0x66, 0x7F, 0x7F, 0x6B, 0x63, 0x00],
    'n': [0x00, 0x00, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x00],
    'o': [0x00, 0x00, 0x3C, 0x66, 0x66, 0x66, 0x3C, 0x00],
    'p': [0x00, 0x00, 0x7C, 0x66, 0x66, 0x7C, 0x60, 0x60],
    'q': [0x00, 0x00, 0x3E, 0x66, 0x66, 0x3E, 0x06, 0x06],
    'r': [0x00, 0x00, 0x7C, 0x66, 0x60, 0x60, 0x60, 0x00],
    's': [0x00, 0x00, 0x3E, 0x60, 0x3C, 0x06, 0x7C, 0x00],
    't': [0x30, 0x30, 0x7C, 0x30, 0x30, 0x36, 0x1C, 0x00],
    'u': [0x00, 0x00, 0x66, 0x66, 0x66, 0x66, 0x3E, 0x00],
    'v': [0x00, 0x00, 0x66, 0x66, 0x66, 0x3C, 0x18, 0x00],
    'w': [0x00, 0x00, 0x63, 0x6B, 0x7F, 0x3E, 0x36, 0x00],
    'x': [0x00, 0x00, 0x66, 0x3C, 0x18, 0x3C, 0x66, 0x00],
    'y': [0x00, 0x00, 0x66, 0x66, 0x66, 0x3E, 0x06, 0x3C],
    'z': [0x00, 0x00, 0x7E, 0x0C, 0x18, 0x30, 0x7E, 0x00],
    '-': [0x00, 0x00, 0x00, 0x7E, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00],
    ',': [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x30],
    '!': [0x18, 0x18, 0x18, 0x18, 0x00, 0x00, 0x18, 0x00],
    '?': [0x3C, 0x66, 0x06, 0x0C, 0x18, 0x00, 0x18, 0x00],
}

class ILI9486Display:
    """Driver melhorado para display ILI9486 320x480"""
    
    def __init__(self, spi, dc, cs, rst, width=320, height=480, rotation=0):
        self.spi = spi
        self.dc = dc
        self.cs = cs
        self.rst = rst
        self.width = width
        self.height = height
        self.rotation = rotation
        
        # Configura pinos
        self.dc.init(Pin.OUT, value=0)
        self.cs.init(Pin.OUT, value=1)
        self.rst.init(Pin.OUT, value=1)
        
        # Buffer para otimização
        self.buffer = bytearray(4096)  # Buffer de 2KB para operações rápidas
        
        # Inicializa display
        self.init_display()
        print("Display ILI9486 inicializado (320x480)")
    
    def init_display(self):
        """Sequência de inicialização completa do ILI9486"""
        # Hardware Reset
        self.rst.value(0)
        utime.sleep_ms(100)
        self.rst.value(1)
        utime.sleep_ms(100)
        
        # Sequência de inicialização ILI9486
        self.write_cmd(0xF1)  # Interface Control
        self.write_data([0x36, 0x04, 0x00, 0x3C, 0x0F, 0x8F])
        
        self.write_cmd(0xF2)  # Interface Control
        self.write_data([0x18, 0xA3, 0x12, 0x02, 0xB2, 0x12, 0xFF, 0x10, 0x00])
        
        self.write_cmd(0xF8)  # Interface Control
        self.write_data([0x21, 0x04])
        
        self.write_cmd(0xF9)  # Interface Control  
        self.write_data([0x00, 0x08])
        
        self.write_cmd(0x36)  # Memory Access Control
        self.write_data([0x48])  # BGR, Row/Column exchange
        
        self.write_cmd(0x3A)  # Pixel Format
        self.write_data([0x55])  # 16-bit RGB565
        
        self.write_cmd(0xC0)  # Power Control 1
        self.write_data([0x0C, 0x02])
        
        self.write_cmd(0xC1)  # Power Control 2
        self.write_data([0x44])
        
        self.write_cmd(0xC5)  # VCOM Control
        self.write_data([0x00, 0x16, 0x80])
        
        self.write_cmd(0xB1)  # Frame Rate Control
        self.write_data([0xB0, 0x11])
        
        self.write_cmd(0xB4)  # Display Inversion Control
        self.write_data([0x02])
        
        self.write_cmd(0xB6)  # Display Function Control
        self.write_data([0x02, 0x22, 0x3B])
        
        self.write_cmd(0xE0)  # Positive Gamma Control
        self.write_data([0x0F, 0x21, 0x1C, 0x0B, 0x0E, 0x08, 0x49, 0x98, 
                         0x38, 0x09, 0x11, 0x03, 0x14, 0x10, 0x00])
        
        self.write_cmd(0xE1)  # Negative Gamma Control  
        self.write_data([0x0F, 0x2F, 0x28, 0x05, 0x07, 0x02, 0x49, 0x48,
                         0x35, 0x04, 0x0B, 0x09, 0x17, 0x30, 0x00])
        
        self.write_cmd(0x11)  # Sleep Out
        utime.sleep_ms(150)
        
        self.write_cmd(0x29)  # Display On
        utime.sleep_ms(50)
        
        # Limpa tela
        self.fill(0x0000)
    
    def write_cmd(self, cmd):
        """Envia comando para o display"""
        self.cs.value(0)
        self.dc.value(0)  # Comando
        self.spi.write(bytearray([cmd]))
        self.cs.value(1)
    
    def write_data(self, data):
        """Envia dados para o display"""
        self.cs.value(0)
        self.dc.value(1)  # Dados
        if isinstance(data, int):
            self.spi.write(bytearray([data]))
        else:
            self.spi.write(bytearray(data))
        self.cs.value(1)
    
    def set_window(self, x0, y0, x1, y1):
        """Define janela de desenho"""
        # Column Address Set
        self.write_cmd(0x2A)
        self.write_data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        
        # Row Address Set
        self.write_cmd(0x2B)
        self.write_data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        
        # Memory Write
        self.write_cmd(0x2C)
    
    def fill(self, color):
        """Preenche toda a tela com uma cor"""
        self.fill_rect(0, 0, self.width, self.height, color)
    
    def fill_rect(self, x, y, width, height, color):
        """Preenche retângulo com cor"""
        if x >= self.width or y >= self.height:
            return
        
        # Ajusta limites
        x1 = min(x + width - 1, self.width - 1)
        y1 = min(y + height - 1, self.height - 1)
        
        if x1 < x or y1 < y:
            return
            
        self.set_window(x, y, x1, y1)
        
        # Prepara cor em bytes
        hi = color >> 8
        lo = color & 0xFF
        
        # Calcula total de pixels
        total_pixels = (x1 - x + 1) * (y1 - y + 1)
        
        # Preenche usando buffer para otimização
        self.cs.value(0)
        self.dc.value(1)
        
        # Preenche buffer com a cor
        for i in range(0, min(len(self.buffer), total_pixels * 2), 2):
            self.buffer[i] = hi
            self.buffer[i + 1] = lo
        
        # Envia dados em chunks
        bytes_per_chunk = len(self.buffer)
        pixels_per_chunk = bytes_per_chunk // 2
        total_bytes = total_pixels * 2
        
        for byte_offset in range(0, total_bytes, bytes_per_chunk):
            chunk_size = min(bytes_per_chunk, total_bytes - byte_offset)
            self.spi.write(self.buffer[:chunk_size])
        
        self.cs.value(1)
    
    def draw_pixel(self, x, y, color):
        """Desenha um pixel"""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        
        self.set_window(x, y, x, y)
        self.write_data([color >> 8, color & 0xFF])
    
    def draw_line(self, x0, y0, x1, y1, color):
        """Desenha linha usando algoritmo de Bresenham"""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        
        while True:
            self.draw_pixel(x0, y0, color)
            
            if x0 == x1 and y0 == y1:
                break
                
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
    
    def draw_char(self, x, y, char, color, size=1, bg_color=None):
        """Desenha um caractere usando fonte bitmap"""
        if char not in FONT_8x8:
            char = ' '  # Substitui caracteres não suportados
        
        bitmap = FONT_8x8[char]
        
        for row in range(8):
            for col in range(8):
                if bitmap[row] & (1 << (7 - col)):
                    # Pixel ativo
                    for sy in range(size):
                        for sx in range(size):
                            self.draw_pixel(x + col * size + sx, 
                                          y + row * size + sy, color)
                elif bg_color is not None:
                    # Pixel de fundo
                    for sy in range(size):
                        for sx in range(size):
                            self.draw_pixel(x + col * size + sx, 
                                          y + row * size + sy, bg_color)
    
    def draw_text(self, x, y, text, color, size=1, bg_color=None):
        """Desenha string de texto"""
        char_width = 8 * size
        current_x = x
        
        for char in text:
            if current_x + char_width > self.width:
                break  # Texto excede largura da tela
            
            self.draw_char(current_x, y, char, color, size, bg_color)
            current_x += char_width
    
    def draw_text_centered(self, text, y, color, size=1, bg_color=None):
        """Desenha texto centralizado horizontalmente"""
        text_width = len(text) * 8 * size
        x = (self.width - text_width) // 2
        self.draw_text(x, y, text, color, size, bg_color)
    
    def draw_text_wrapped(self, x, y, text, color, size=1, max_width=None, bg_color=None):
        """Desenha texto com quebra de linha automática"""
        if max_width is None:
            max_width = self.width - x
        
        char_width = 8 * size
        char_height = 8 * size
        chars_per_line = max_width // char_width
        
        words = text.split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (' ' if current_line else '') + word
            if len(test_line) <= chars_per_line:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        # Desenha cada linha
        for i, line in enumerate(lines):
            line_y = y + (i * char_height * 1.2)  # Espaçamento entre linhas
            if line_y + char_height > self.height:
                break  # Texto excede altura da tela
            self.draw_text(x, int(line_y), line, color, size, bg_color)
        
        return len(lines) * char_height * 1.2  # Retorna altura total usada
    
    def draw_rect(self, x, y, width, height, color, fill=False):
        """Desenha retângulo"""
        if fill:
            self.fill_rect(x, y, width, height, color)
        else:
            # Bordas do retângulo
            self.draw_line(x, y, x + width - 1, y, color)  # Top
            self.draw_line(x, y, x, y + height - 1, color)  # Left
            self.draw_line(x + width - 1, y, x + width - 1, y + height - 1, color)  # Right
            self.draw_line(x, y + height - 1, x + width - 1, y + height - 1, color)  # Bottom
    
    def draw_circle(self, cx, cy, radius, color, fill=False):
        """Desenha círculo usando algoritmo de Bresenham"""
        x = 0
        y = radius
        d = 3 - 2 * radius
        
        def draw_circle_points(cx, cy, x, y, color, fill):
            if fill:
                self.draw_line(cx - x, cy + y, cx + x, cy + y, color)
                self.draw_line(cx - x, cy - y, cx + x, cy - y, color)
                self.draw_line(cx - y, cy + x, cx + y, cy + x, color)
                self.draw_line(cx - y, cy - x, cx + y, cy - x, color)
            else:
                points = [
                    (cx + x, cy + y), (cx - x, cy + y), (cx + x, cy - y), (cx - x, cy - y),
                    (cx + y, cy + x), (cx - y, cy + x), (cx + y, cy - x), (cx - y, cy - x)
                ]
                for px, py in points:
                    self.draw_pixel(px, py, color)
        
        draw_circle_points(cx, cy, x, y, color, fill)
        
        while y >= x:
            x += 1
            if d > 0:
                y -= 1
                d = d + 4 * (x - y) + 10
            else:
                d = d + 4 * x + 6
            draw_circle_points(cx, cy, x, y, color, fill)
    
    def clear(self, color=0x0000):
        """Limpa tela com cor especificada (padrão: preto)"""
        self.fill(color)
    
    def set_brightness(self, level):
        """Controla brilho do backlight (se suportado)"""
        # Esta função dependeria de hardware adicional (PWM no pino LED)
        # Por simplicidade, apenas liga/desliga
        if level > 0:
            print(f"Backlight: ON (nivel {level})")
        else:
            print("Backlight: OFF")
    
    def scroll_vertical(self, lines):
        """Rolagem vertical (implementação básica)"""
        # Para uma implementação completa, seria necessário usar
        # comandos específicos do ILI9486 para scroll de hardware
        print(f"Scroll vertical: {lines} linhas")
    
    def invert_display(self, invert=True):
        """Inverte cores do display"""
        if invert:
            self.write_cmd(0x21)  # Display Inversion On
        else:
            self.write_cmd(0x20)  # Display Inversion Off
    
    def sleep(self, enable=True):
        """Coloca display em modo sleep"""
        if enable:
            self.write_cmd(0x10)  # Sleep In
            print("Display: Sleep mode ON")
        else:
            self.write_cmd(0x11)  # Sleep Out
            utime.sleep_ms(150)
            print("Display: Sleep mode OFF")
    
    def display_off(self):
        """Desliga display"""
        self.write_cmd(0x28)  # Display Off
        print("Display: OFF")
    
    def display_on(self):
        """Liga display"""
        self.write_cmd(0x29)  # Display On
        print("Display: ON")

# Cores pré-definidas em RGB565
class Colors:
    BLACK = 0x0000
    WHITE = 0xFFFF
    RED = 0xF800
    GREEN = 0x07E0
    BLUE = 0x001F
    YELLOW = 0xFFE0
    MAGENTA = 0xF81F
    CYAN = 0x07FF
    ORANGE = 0xFC00
    PURPLE = 0x8010
    GRAY = 0x7BEF
    DARK_GRAY = 0x39E7
    LIGHT_GRAY = 0xBDF7
    BROWN = 0xA145
    PINK = 0xF97F
    LIME = 0x87E0
    INDIGO = 0x4810
    GOLD = 0xFEA0

def rgb565(r, g, b):
    """Converte RGB (0-255) para RGB565"""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

def test_display(display):
    """Função de teste para o display"""
    print("Testando display ILI9486...")
    
    # Teste 1: Cores básicas
    print("Teste 1: Preenchimento com cores")
    display.fill(Colors.RED)
    utime.sleep(1)
    display.fill(Colors.GREEN)
    utime.sleep(1)
    display.fill(Colors.BLUE)
    utime.sleep(1)
    display.fill(Colors.BLACK)
    
    # Teste 2: Texto
    print("Teste 2: Renderização de texto")
    display.draw_text_centered("MAGIC MIRROR", 100, Colors.WHITE, 3)
    display.draw_text_centered("Teste de Display", 150, Colors.YELLOW, 2)
    display.draw_text(10, 200, "Fonte tamanho 1", Colors.GREEN, 1)
    display.draw_text(10, 220, "Fonte tamanho 2", Colors.CYAN, 2)
    display.draw_text(10, 250, "Fonte tamanho 3", Colors.MAGENTA, 3)
    utime.sleep(3)
    
    # Teste 3: Formas geométricas
    print("Teste 3: Formas geométricas")
    display.clear()
    display.draw_rect(50, 50, 100, 80, Colors.RED)
    display.draw_rect(200, 50, 100, 80, Colors.GREEN, fill=True)
    display.draw_circle(160, 200, 30, Colors.BLUE)
    display.draw_circle(160, 300, 40, Colors.YELLOW, fill=True)
    utime.sleep(3)
    
    # Teste 4: Texto com quebra de linha
    print("Teste 4: Texto com quebra automática")
    display.clear()
    long_text = "Este e um texto longo que devera ser quebrado automaticamente em multiplas linhas para testar a funcao de texto com quebra de linha."
    display.draw_text_wrapped(10, 50, long_text, Colors.WHITE, 2, 300)
    utime.sleep(3)
    
    display.clear()
    print("Teste concluído!")

# Exemplo de uso
if __name__ == "__main__":
    # Configuração SPI
    spi = SPI(0, baudrate=40000000, sck=Pin(18), mosi=Pin(19))
    
    # Criar display
    display = ILI9486Display(
        spi=spi,
        dc=Pin(16),
        cs=Pin(17), 
        rst=Pin(20),
        width=320,
        height=480
    )
    
    # Executar testes
    test_display(display)
# st7735_test.py
# Raspberry Pi Pico(W) + ST7735 SPI TFT Test (Multi-display with demux or multiple CS pins)
# MicroPython code with minimal ST7735 driver

from machine import Pin, SPI, PWM
import time, framebuf

# =======================
# Pin Configuration (GPIO numbers)
# =======================

PIN_SCK   = const(18)  # SPI0 SCK
PIN_MOSI  = const(19)  # SPI0 MOSI(TX)
PIN_CS    = [7,8,9]  # Chip Select. any GPIO
PIN_DC    = const(14)  # Data/Command (A0) RED
PIN_RST   = const(15)  # Reset yellow

# Display resolution
WIDTH  = 128
HEIGHT = 160

# SPI configuration
SPI_BAUD  = 20_000_000  # 20~40 MHz (안정성 고려)
ROTATION  = 0           # 0~3 선택
COLOR_ORDER_BGR = False # 색 순서 반전 시 True

# ====== Color helper ======
def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

WHITE   = rgb565(255,255,255)
BLACK   = rgb565(0,0,0)
RED     = rgb565(255,0,0)
GREEN   = rgb565(0,255,0)
BLUE    = rgb565(0,0,255)
YELLOW  = rgb565(255,255,0)
CYAN    = rgb565(0,255,255)
MAGENTA = rgb565(255,0,255)

# ====== Minimal ST7735 driver (multi CS 지원) ======
class ST7735:
    def __init__(self, spi, cs, dc, rst, width, height, rotation=0, bgr=False, xstart=0, ystart=0):
        self.spi = spi
        # 디먹스 입력핀(7,8,9)은 '항상' 준비해둠
        self._demux_pins = {p: Pin(p, Pin.OUT, value=0) for p in PIN_CS}
        # 이 인스턴스가 요구하는 비트 조합: 리스트에 포함된 핀은 HIGH, 그 외는 LOW
        self._cs_bits = set(cs)  # 예: []=000, [7]=001, [8]=010, [7,8]=011, [9]=100 ...

        self.dc  = Pin(dc, Pin.OUT, value=0)
        self.rst = Pin(rst, Pin.OUT, value=1)

        self.width  = width
        self.height = height
        self.rotation = rotation
        self.bgr = bgr
        self.xstart = xstart
        self.ystart = ystart

        self.buffer = bytearray(self.width * self.height * 2)
        self.fb = framebuf.FrameBuffer(self.buffer, self.width, self.height, framebuf.RGB565)

        # 글리프 버퍼 유지
        self._gbuf = bytearray(8 * 8 * 2)
        self._gfb  = framebuf.FrameBuffer(self._gbuf, 8, 8, framebuf.RGB565)
        self._WHITE = 0xFFFF
        self._BLACK = 0x0000
    
    def select(self, idx):
        """선택할 디스플레이 인덱스를 지정"""
        # 모든 CS 핀 HIGH로 초기화
        for pin in self.cs_pins:
            pin(1)
        # 지정된 CS만 LOW
        self.cs_pins 
        self.active_idx = idx

    def deselect(self):
        """모든 CS 해제"""
        for pin in self.cs_pins:
            pin(1)
    
    def _apply_demux_select(self):
        """이 인스턴스에 해당하는 디먹스 주소(7,8,9)를 세팅합니다."""
        # 주의: 항상 모든 입력을 명시적으로 0/1로 설정 (부동 방지)
        for p in PIN_CS:
            self._demux_pins[p](1 if p in self._cs_bits else 0)
        # (필요 시 74HC138의 Enable 핀: G1=HIGH, /G2A=/G2B=LOW로 고정 연결)
        
        time.sleep_us(3)

    def _reset(self):
        self.rst(0)
        time.sleep_ms(50)
        self.rst(1)
        time.sleep_ms(120)

    def _cmd(self, c):
        self._apply_demux_select()  # 먼저 해당 패널 선택
        self.dc(0)
        self.spi.write(bytearray([c]))

    def _data(self, d):
        self._apply_demux_select()
        self.dc(1)
        self.spi.write(bytearray([d]))

    def _init_regs(self):

        self._cmd(0x11)  # SLPOUT
        time.sleep_ms(120)

        self._cmd(0x3A)  # COLMOD: Pixel format
        self._data(0x05) # 16-bit color

        madctl = 0x00
        if self.rotation == 1:
            madctl = 0x60  # MV|MX
        elif self.rotation == 2:
            madctl = 0xC0  # MY|MX
        elif self.rotation == 3:
            madctl = 0xA0  # MV|MY
        if self.bgr:
            madctl |= 0x08

        self._cmd(0x36)
        self._data(madctl)

        self._cmd(0x20)  # INVON
        self._cmd(0x13)  # NORON
        self._cmd(0x29)  # DISPON
        time.sleep_ms(50)

        self._set_window(0, 0, self.width-1, self.height-1)
    
    def init_panel(self):
        """선택된 패널만 SWRESET으로 개별 초기화"""
        self._cmd(0x01)          # SWRESET (선택된 CS에만 적용)
        time.sleep_ms(150)
        self._init_regs()
        self.set_rotation(self.rotation)  # 창/가로세로 업데이트

    def _set_window(self, x0, y0, x1, y1):
        if self.rotation in (0, 2):
            xs, ys = self.xstart, self.ystart
        else:
            xs, ys = self.ystart, self.xstart

        x0 += xs; x1 += xs
        y0 += ys; y1 += ys

        self._cmd(0x2A)
        self._data(0x00); self._data(x0 & 0xFF)
        self._data(0x00); self._data(x1 & 0xFF)
        self._cmd(0x2B)
        self._data(0x00); self._data(y0 & 0xFF)
        self._data(0x00); self._data(y1 & 0xFF)
        self._cmd(0x2C)
        
    def set_rotation(self, r):
        self.rotation = r & 3
        madctl = 0x00
        if self.rotation == 0:
            madctl = 0x00
            self.width, self.height = self.width, self.height
        elif self.rotation == 1:
            madctl = 0x60 # MV|MX
            self.width, self.height = self.height, self.width
        elif self.rotation == 2:
            madctl = 0xC0 # MY|MX
            self.width, self.height = self.width, self.height
        elif self.rotation == 3:
            madctl = 0xA0 # MV|MY
            self.width, self.height = self.height, self.width
        
        if self.bgr:
            madctl |= 0x08

        self._cmd(0x36); self._data(madctl)
        self.fb = framebuf.FrameBuffer(self.buffer, self.width, self.height, framebuf.RGB565) # 회전 바뀌면 전체 윈도우 재설정
        self._set_window(0, 0, self.width-1, self.height-1)

    def fill(self, col):
        self.fb.fill(col)

    def text(self, s, x, y, col=WHITE):
        self.fb.text(s, x, y, col)

    def rect(self, x, y, w, h, col):
        self.fb.rect(x, y, w, h, col)

    def fill_rect(self, x, y, w, h, col):
        self.fb.fill_rect(x, y, w, h, col)

    def hline(self, x, y, w, col):
        self.fb.hline(x, y, w, col)

    def vline(self, x, y, h, col):
        self.fb.vline(x, y, h, col)

    def show(self):
        # 전체 창 지정
        self._apply_demux_select()
        self._set_window(0, 0, self.width - 1, self.height - 1)

        n = len(self.buffer)
        if not hasattr(self, "_txbuf") or len(self._txbuf) != n:
            self._txbuf = bytearray(n)

        src = memoryview(self.buffer)
        dst = memoryview(self._txbuf)

        # RGB565 엔디안 스왑
        i = 0
        while i < n:
            b0 = src[i]; b1 = src[i+1]
            dst[i]   = b1
            dst[i+1] = b0
            i += 2

        self._apply_demux_select()
        self.dc(1)
        self.spi.write(dst)

    def text_scaled(self, s, x, y, col, scale=2, bg=None, spacing=0):
        cx = x
        adv = (8 + spacing) * scale
        for ch in s:
            self._gfb.fill(self._BLACK)
            self._gfb.text(ch, 0, 0, self._WHITE)
            if bg is not None:
                self.fb.fill_rect(cx, y, 8*scale, 8*scale, bg)
            for yy in range(8):
                for xx in range(8):
                    if self._gfb.pixel(xx, yy) == self._WHITE:
                        x0 = cx + xx*scale
                        y0 = y  + yy*scale
                        self.fb.fill_rect(x0, y0, scale, scale, col)
            cx += adv

    def draw_bmp24(self, path, x=0, y=0, colkey=None):
        def _rgb888_to_565(r, g, b):
            return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

        with open(path, "rb") as f:
            if f.read(2) != b"BM":
                raise ValueError("Not a BMP")
            f.read(8)  # file size + reserved
            pixel_offset = int.from_bytes(f.read(4), "little")

            dib = int.from_bytes(f.read(4), "little")
            if dib < 40:
                raise ValueError("Unsupported DIB header")

            width  = int.from_bytes(f.read(4), "little", True)
            height = int.from_bytes(f.read(4), "little", True)
            planes = int.from_bytes(f.read(2), "little")
            bpp    = int.from_bytes(f.read(2), "little")
            comp   = int.from_bytes(f.read(4), "little")

            if bpp != 24 or comp != 0:
                raise ValueError("Need 24-bit uncompressed BMP")

            skip = dib - 16
            if skip > 0:
                f.read(skip)

            top_down = False
            if height < 0:
                height = -height
                top_down = True

            row_bytes = ((width * 3 + 3) // 4) * 4
            f.seek(pixel_offset)

            for row in range(height):
                bmp_row = row if top_down else (height - 1 - row)
                dst_y = y + bmp_row
                line = f.read(row_bytes)
                if not (0 <= dst_y < self.height):
                    continue
                idx = 0
                for col in range(width):
                    dst_x = x + col
                    if 0 <= dst_x < self.width:
                        b = line[idx]; g = line[idx+1]; r = line[idx+2]
                        if (colkey is None) or (r, g, b) != colkey:
                            self.fb.pixel(dst_x, dst_y, _rgb888_to_565(r, g, b))
                    idx += 3

# ====== Main Test ======
def test_display():
    spi = SPI(0, baudrate=SPI_BAUD, polarity=0, phase=0,
              sck=Pin(PIN_SCK), mosi=Pin(PIN_MOSI))

    # 전체 하드웨어 리셋(공유 RST): 한 번만
    rst = Pin(PIN_RST, Pin.OUT, value=0)
    time.sleep_ms(50)
    rst(1)
    time.sleep_ms(120)

    # 필요 시 BL PWM
    try:
        bl = PWM(Pin(PIN_BL)); bl.freq(1000); bl.duty_u16(65535)
    except:
        pass

    # 패널 인스턴스 생성
    tft_list = []
    tft_list.append(ST7735(spi, cs=[],      dc=PIN_DC, rst=PIN_RST, width=WIDTH, height=HEIGHT, rotation=ROTATION, bgr=False))      # ABC=000 -> Y0
    tft_list.append(ST7735(spi, cs=[7],     dc=PIN_DC, rst=PIN_RST, width=WIDTH, height=HEIGHT, rotation=ROTATION, bgr=False))      # 001 -> Y1
    tft_list.append(ST7735(spi, cs=[8],     dc=PIN_DC, rst=PIN_RST, width=WIDTH, height=HEIGHT, rotation=ROTATION, bgr=False))      # 010 -> Y2
    tft_list.append(ST7735(spi, cs=[7,8],   dc=PIN_DC, rst=PIN_RST, width=WIDTH, height=HEIGHT, rotation=ROTATION, bgr=False))      # 011 -> Y3

    # 각 패널 SWRESET + 레지스터 초기화
    for tft in tft_list:
        tft.init_panel()
    
    
    # 테스트 그리기
    colors = [GREEN, YELLOW, RED, RED]
    
    # 디스플레이 초기 상태
    for i, tft in enumerate(tft_list):
        tft.set_rotation(1)
        tft.fill(RED)
        tft.draw_bmp24("image_50_medium.bmp", x=10, y=10, colkey=(255, 255, 255))
        tft.show()

    
    for i, tft in enumerate(tft_list):
        tft.fill(colors[i])
        tft.text("99999999", 80, 20, BLACK)
        tft.text("Kim Tae Gyun", 60, 40, BLACK)
        tft.text_scaled("SC", 65, 75, BLACK, scale=5,)
        tft.draw_bmp24("image_50_medium.bmp", x=10, y=10, colkey=(255, 255, 255))
        tft.show()


if __name__ == "__main__":
    test_display()


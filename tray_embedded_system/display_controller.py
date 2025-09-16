# display_controller.py
from machine import Pin, SPI, PWM
from display import *


class displayController:
    tft_list = []
    info_list = [] # info -> [number, name, route]
    CURRENT = 0
    
    def __init__(self):
        spi = SPI(0, baudrate=20_000_000, polarity=0, phase=0,
              sck=Pin(18), mosi=Pin(19))

        # 하드웨어 리셋 한 번
        rst = Pin(15, Pin.OUT, value=0); import time; time.sleep_ms(50); rst(1); time.sleep_ms(120)
        
        # 패널 0~3 생성
        self.tft_list.append(ST7735(spi, cs=[],      dc=PIN_DC, rst=PIN_RST, width=WIDTH, height=HEIGHT, rotation=ROTATION, bgr=False))      # ABC=000 -> Y0
        self.tft_list.append(ST7735(spi, cs=[7],     dc=PIN_DC, rst=PIN_RST, width=WIDTH, height=HEIGHT, rotation=ROTATION, bgr=False))      # 001 -> Y1
        self.tft_list.append(ST7735(spi, cs=[8],     dc=PIN_DC, rst=PIN_RST, width=WIDTH, height=HEIGHT, rotation=ROTATION, bgr=False))      # 010 -> Y2
        self.tft_list.append(ST7735(spi, cs=[7,8],   dc=PIN_DC, rst=PIN_RST, width=WIDTH, height=HEIGHT, rotation=ROTATION, bgr=False))      # 011 -> Y3

        # 각 패널 SWRESET + 레지스터 초기화
        for tft in self.tft_list:
            tft.init_panel()

        
        
        self.display_init()

    def display_init(self):
        # 디스플레이 초기 상태
        for i, tft in enumerate(self.tft_list):
            tft.set_rotation(1)
            tft.fill(RED)
            tft.draw_bmp24("image_50_medium.bmp", x=10, y=10, colkey=(255, 255, 255))
            tft.show()
            
    def paint_the_town_yellow(self, info):
        #바코드 스캐너로 주사기 qr 인식
        self.tft_list[self.CURRENT].fill(YELLOW)
        self.tft_list[self.CURRENT].text(info[0], 80, 20, BLACK)
        self.tft_list[self.CURRENT].text(info[1], 60, 40, BLACK)
        self.tft_list[self.CURRENT].draw_bmp24("image_50_medium.bmp", x=10, y=10, colkey=(255, 255, 255))
        self.tft_list[self.CURRENT].show()
        self.CURRENT = (self.CURRENT + 1) % 4
        self.info_list.append(info)

    def paint_the_town_green(self, info):
        #환자 qr인식 성공
        for i in range(len(self.info_list)):
            if self.info_list[i][0] == info[0]:
                self.tft_list[i].fill(GREEN)
                self.tft_list[i].text(info[0], 80, 20, BLACK)
                self.tft_list[i].text(info[1], 60, 40, BLACK)
                self.tft_list[i].text_scaled(info[2], 65, 75, BLACK, scale=5,)
                self.tft_list[i].draw_bmp24("image_50_medium.bmp", x=10, y=10, colkey=(255, 255, 255))
                self.tft_list[i].show()
            else:
                continue
            
    
            



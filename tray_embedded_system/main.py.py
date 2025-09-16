#main.py
import uasyncio as asyncio
from micropython import const
from display_controller import displayController
from gm_805s import GM805
from ble_qr_receiver import BLEQRReceiver
from machine import UART, Pin
import time


patient_numbers = []

async def consumer(receiver: BLEQRReceiver, display: displayController):
    global patient_numbers
    while True:
        msg = await receiver.get_msg()
        print(msg)
        info = msg.split('-') # number, name, route
        
        if info[0] not in patient_numbers:
            patient_numbers.append(info[0])
            display.paint_the_town_green(info)


async def main_pico():

    last_patient = None
    UART_ID = 0   # Pico: UART0=(GP0,GP1), UART1=(GP8,GP9) 등
    TX_PIN  = 12   # Pico TX -> GM805S RX
    RX_PIN  = 13  # Pico RX -> GM805S TX
    full_display = displayController()    
    scanner = GM805(uart_id=UART_ID, tx=TX_PIN, rx=RX_PIN, baudrate=9600)
    qr_receiver = BLEQRReceiver()
    asyncio.create_task(consumer(qr_receiver, full_display))
    
    scanner.set_command_trigger_mode(persist=False)

    print("GM805S async test. Triggering & awaiting reads...")
    while True:
        scanner.trigger_fire_and_forget()
        await asyncio.sleep_ms(50)

        code = await scanner.read_code_async(timeout_ms=2000, idle_gap_ms=40)
        code[:-1]
        if code:
            split_code = code.split('-')
            if len(split_code) > 2 and last_patient != split_code[0]:
                split_code[2] = split_code[2][0:2]
                print(split_code)
                last_patient = split_code[0]
                full_display.paint_the_town_yellow(split_code)
        else:
            print("No read")

        await asyncio.sleep_ms(2000)
    
if __name__ == "__main__":
    asyncio.run(main_pico())


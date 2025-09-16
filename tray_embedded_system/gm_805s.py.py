# gm805.py (MicroPython / Raspberry Pi Pico)
from machine import UART, Pin
import time
import uasyncio as asyncio

class GM805:
    # ---- Protocol constants (from manual) ----
    HDR1 = b'\x7E\x00'         # command header
    HDR2 = b'\x02\x00'         # response header
    TYPE_READ  = 0x07          # Read zone bit
    TYPE_WRITE = 0x08          # Write zone bit
    TYPE_SAVE  = 0x09          # Save zone bits to internal flash
    # Zone addresses (subset)
    ZONE_MODE_ADDR   = 0x0000  # bits1-0: 00 Manual, 01 Command, 10 Continuous, 11 Induction
    ZONE_TRIGGER_ADDR= 0x0002  # bit0: Command trigger flag (auto-clear after scan)

    def __init__(self, uart_id, tx, rx, baudrate=9600, trigger_pin=None):
        self.uart = UART(
            uart_id,
            baudrate=baudrate, bits=8, parity=None, stop=1,
            tx=Pin(tx), rx=Pin(rx),
            timeout=100, timeout_char=20
        )
        self.trig = Pin(trigger_pin, Pin.OUT, value=1) if trigger_pin is not None else None

    # ---- CRC-CCITT (0x1021, init 0x0000) per manual; but device also accepts 0xAB,0xCD if CRC check not required ----
    def _crc_ccitt(self, data: bytes) -> bytes:
        crc = 0
        for b in data:
            crc ^= (b << 8) & 0xFFFF
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    def _send(self, payload: bytes, use_crc=False, wait_ack=True, ack_timeout_ms=300):
        crc = self._crc_ccitt(payload) if use_crc else b'\xAB\xCD'
        pkt = payload + crc
        self.uart.write(pkt)
        if not wait_ack:
            return None
        t0 = time.ticks_ms()
        buf = b''
        while time.ticks_diff(time.ticks_ms(), t0) < ack_timeout_ms:
            if self.uart.any():
                buf += self.uart.read()
                # minimal ack check: look for response header
                i = buf.find(self.HDR2)
                if i >= 0 and len(buf) >= i + 4:
                    return buf
            time.sleep_ms(5)
        return buf or None  # may be None if nothing received

    # ---- Zone bit R/W ----
    def read_zone(self, addr: int, length: int = 1, use_crc=False):
        # Input: {HDR1}{TYPE}{LEN}{ADDR_H}{ADDR_L}{COUNT}
        payload = self.HDR1 + bytes([self.TYPE_READ, 0x01]) + bytes([(addr >> 8) & 0xFF, addr & 0xFF, length & 0xFF])
        resp = self._send(payload, use_crc=use_crc, wait_ack=True)
        if not resp:
            return None
        i = resp.find(self.HDR2)
        if i < 0 or len(resp) < i + 4:
            return None
        typ = resp[i+2]
        ln  = resp[i+3]
        if typ == 0x00 and len(resp) >= i + 4 + ln:
            return resp[i+4:i+4+ln]
        return None

    def write_zone(self, addr: int, data_bytes: bytes, use_crc=False):
        ln = len(data_bytes) & 0xFF
        payload = self.HDR1 + bytes([self.TYPE_WRITE, ln]) + bytes([(addr >> 8) & 0xFF, addr & 0xFF]) + data_bytes
        return self._send(payload, use_crc=use_crc, wait_ack=True)

    def save_zone_to_flash(self, use_crc=False):
        # Save entire zone-bit list (required for persistence)
        payload = self.HDR1 + bytes([self.TYPE_SAVE, 0x01, 0x00, 0x00, 0x00])
        return self._send(payload, use_crc=use_crc, wait_ack=True)

    # ---- Operating helpers ----
    def set_command_trigger_mode(self, persist=True):
        cur = self.read_zone(self.ZONE_MODE_ADDR) or b'\x00'
        new = (cur[0] & 0xFC) | 0x01  # bits1-0 = 01 (Command Triggered Mode)
        if new != cur[0]:
            self.write_zone(self.ZONE_MODE_ADDR, bytes([new]))
            if persist:
                self.save_zone_to_flash()

    def trigger_once(self):
        # Software trigger = set bit0 of 0x0002 to 1 (auto-reset by device after a successful read)
        val = self.read_zone(self.ZONE_TRIGGER_ADDR) or b'\x00'
        self.write_zone(self.ZONE_TRIGGER_ADDR, bytes([val[0] | 0x01]))

    def heartbeat(self):
        # Recommended ~10s 주기로 송신 (응답 없으면 링크 상태 점검) — 포맷은 매뉴얼 표 참고
        hb = bytes([0x7E,0x00,0x0A,0x01,0x00,0x00,0x00,0x30,0x1A,0x03,0x00,0x00,0x01,0x00,0x33,0x31])
        self.uart.write(hb)

    def read_code(self, timeout_ms=1500, idle_gap_ms=40):
        """CR/LF가 오든, 없는 연속 바이트든 모두 수신. 성공 시 str 반환, 없으면 None."""
        t0 = time.ticks_ms()
        buf = bytearray()
        last = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
            if self.uart.any():
                b = self.uart.read(1)
                if not b:
                    continue
                buf += b
                last = time.ticks_ms()
                if b == b'\n':  # CR/LF 종단 지원
                    break
            else:
                if buf and time.ticks_diff(time.ticks_ms(), last) > idle_gap_ms:
                    break
                time.sleep_ms(2)
    
        if not buf:
            return None
        
        s = bytes(buf).strip()
        
        try:
            return s.decode("utf-8")
        except:
            try:
                return s.decode("ascii", "ignore")
            except:
                return s  # raw bytes fallback
            
    async def read_code_async(self, timeout_ms=1500, idle_gap_ms=40):
        t0 = time.ticks_ms()
        buf = bytearray()
        last = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
            if self.uart.any():
                b = self.uart.read(1)
                if b:
                    buf += b
                    last = time.ticks_ms()
                    if b == b'\n':  # CR/LF로 끝나는 형식도 지원
                        break
            else:
                if buf and time.ticks_diff(time.ticks_ms(), last) > idle_gap_ms:
                    break
                # ★ 여기서 이벤트 루프에 양보
                await asyncio.sleep_ms(2)
        if not buf:
            return None
        s = bytes(buf).strip()
        for enc in ("utf-8", "ascii"):
            try:
                return s.decode(enc, "ignore")
            except:
                pass
        return s  # raw bytes fallback

    def trigger_fire_and_forget(self):
        # ZONE_TRIGGER_ADDR에 0x01 쓰기 패킷을 직접 만들어 ACK 미대기 송신
        ln = 1
        payload = (
            self.HDR1 +
            bytes([self.TYPE_WRITE, ln]) +
            bytes([(self.ZONE_TRIGGER_ADDR >> 8) & 0xFF, self.ZONE_TRIGGER_ADDR & 0xFF]) +
            b'\x01'
        )
        self._send(payload, use_crc=False, wait_ack=False)  # ★ ACK 미대기


# -------- Example usage --------
def test_gm_805s():
    UART_ID = 0   # Pico: UART0=(GP0,GP1), UART1=(GP8,GP9) 등
    TX_PIN  = 12   # Pico TX -> GM805S RX
    RX_PIN  = 13   # Pico RX -> GM805S TX
    scanner = GM805(uart_id=UART_ID, tx=TX_PIN, rx=RX_PIN, baudrate=9600)

    # (선택) 명령 트리거 모드로 전환 후 저장
    scanner.set_command_trigger_mode(persist=False)

    print("GM805S ready. Triggering & reading...")
    while True:
        # 소프트 트리거 한 번
        scanner.trigger_once()

        # 바코드 수신 대기
        code = scanner.read_code(timeout_ms=2000)
        if code:
            print("BARCODE:", code)
        else:
            print("No read")
        time.sleep(2)

async def main_pico():
    # 핀은 동기 테스트와 동일
    UART_ID = 0     # Pico: UART0=(GP0,GP1)
    TX_PIN  = 12    # Pico TX -> GM805S RX
    RX_PIN  = 13    # Pico RX -> GM805S TX

    scanner = GM805(uart_id=UART_ID, tx=TX_PIN, rx=RX_PIN, baudrate=9600)

    # (선택) 커맨드 트리거 모드로 전환 (영구 저장은 False)
    scanner.set_command_trigger_mode(persist=False)

    print("GM805S async test. Triggering & awaiting reads...")
    while True:
        # ★ 비블로킹 트리거: ACK 미대기(fire-and-forget)
        scanner.trigger_fire_and_forget()
        # 트리거 스파밍 방지 약간의 간격
        await asyncio.sleep_ms(50)

        # ★ 비동기 수신
        code = await scanner.read_code_async(timeout_ms=2000, idle_gap_ms=40)

        if code:
            print("BARCODE:", code)
        else:
            print("No read")

        # 다음 트리거 전 쿨다운(환경에 맞게 조정)
        await asyncio.sleep_ms(2000)

if __name__ == "__main__":
    asyncio.run(main_pico())
    #test_gm_805s()
    


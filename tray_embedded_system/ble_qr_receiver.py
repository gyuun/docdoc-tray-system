import bluetooth
import time
import micropython
from micropython import const
import uasyncio as asyncio
from ble_advertising import advertising_payload

_IRQ_CENTRAL_CONNECT    = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE        = const(3)

# QR코드 값 수신을 위한 UUID 정의
_QR_SERVICE_UUID = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef0")
_QR_RX_UUID      = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef1")

_QR_SERVICE = (
    _QR_SERVICE_UUID,
    (
        (_QR_RX_UUID, bluetooth.FLAG_WRITE,),  # 앱에서 Write 가능
    ),
)

class BLEQRReceiver:
    def __init__(self, name="PICO_QR", inbox_max=16):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)

        ((self._rx_handle,),) = self._ble.gatts_register_services((_QR_SERVICE,))
        try:
            self._ble.gatts_set_buffer(self._rx_handle, 512, True)
        except:
            pass
        
        self._payload = advertising_payload(name=name, services=[_QR_SERVICE_UUID])
        self._advertise()

        # Queue 대체: 내부 버퍼 + 신호 플래그
        self._inbox = []
        self._inbox_max = inbox_max
        # 일부 빌드엔 Event가 없을 수 있으니 ThreadSafeFlag 사용
        self._flag = asyncio.ThreadSafeFlag()
        self._scheduled = False

    def _irq(self, event, data):
        if event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._rx_handle:
                msg = self._ble.gatts_read(self._rx_handle).decode("utf-8", "ignore")
                # IRQ에서는 짧게: 버퍼 넣고 schedule만
                if len(self._inbox) >= self._inbox_max:
                    self._inbox.pop(0)  # 오래된 것 드롭
                self._inbox.append(msg)
                if not self._scheduled:
                    self._scheduled = True
                    micropython.schedule(self._signal, 0)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._advertise()

    def _signal(self, _):
        self._scheduled = False
        # 대기 중 태스크 깨우기 (latched, 다음 wait에도 잘 동작)
        try:
            self._flag.set()
        except Exception as e:
            print("flag set error:", e)

    def _advertise(self, interval_us=500_000):
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

    async def get_msg(self):
        """메시지 하나를 비동기로 가져옵니다."""
        while True:
            if self._inbox:
                return self._inbox.pop(0)
            await self._flag.wait()   # 신호 대기


async def consumer(receiver: BLEQRReceiver):
    while True:
        msg = await receiver.get_msg()
        print("QR:", msg)

async def main():
    r = BLEQRReceiver()
    asyncio.create_task(consumer(r))
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
    




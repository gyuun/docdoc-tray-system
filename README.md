# docdoc-tray-system
2025 PNU Medical Hackathon
# docdoc-tray-system

스마트 주사기 트레이 시스템. **모바일 앱(Flutter)**이 QR 코드를 스캔해 **BLE**로 **Raspberry Pi Pico W (MicroPython)** 트레이에 문자열을 전송하고, 트레이는 수신한 정보를 **디스플레이**에 표시합니다.

> 2025 PNU Medical Hackathon 프로젝트

---

## 목차
- [개요](#개요)
- [아키텍처](#아키텍처)
- [디렉토리 구조](#디렉토리-구조)
- [빠른 시작 (Quick Start)](#빠른-시작-quick-start)
  - [Tray (Pico W / MicroPython)](#tray-pico-w--micropython)
  - [Mobile App (Flutter)](#mobile-app-flutter)
- [BLE 프로파일](#ble-프로파일)
- [환경변수 / 설정](#환경변수--설정)
- [개발/테스트 팁](#개발테스트-팁)
- [문제해결 (Troubleshooting)](#문제해결-troubleshooting)
- [로드맵](#로드맵)
- [라이선스](#라이선스)

---

## 개요
- **목적**: QR 인식 → BLE 전송 → 트레이 디스플레이 표시까지의 전체 플로우를 단순/신뢰성 있게 구현합니다.
- **구성**:
  - **Flutter 앱**: 카메라로 QR 스캔 → BLE Central로 트레이 검색/연결 → 문자열 Write 전송
  - **Pico W (MicroPython)**: BLE Peripheral(GATT 서버) → 문자열 수신 → 디스플레이 업데이트

---

## 아키텍처

```text
+------------------+           BLE (GATT Write)            +-------------------------+
|  Flutter Mobile  | ------------------------------------> |   Pico W (MicroPython)  |
| - QR Scanner     |                                        | - BLE Peripheral (RX)   |
| - BLE Central    | <-----------(optional Notify)--------- | - Display Controller    |
| - UI/Status      |                                        | - ST7735/77xx etc.      |
+------------------+                                        +-------------------


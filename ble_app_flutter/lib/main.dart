import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:qr_code_scanner/qr_code_scanner.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // 개발 중에는 verbose로 보셔도 됩니다.
  FlutterBluePlus.setLogLevel(LogLevel.info);
  runApp(const QRBleApp());
}

class QRBleApp extends StatelessWidget {
  const QRBleApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  // ==== 프로젝트 고정값 ====
  // Pico의 GATT UUID (ble_test.py와 동일)
  static const String serviceUuid = "12345678-1234-5678-1234-56789abcdef0";
  static const String charUuid    = "12345678-1234-5678-1234-56789abcdef1";
  static const String targetName  = "PICO_QR"; // 표시용(필수 아님)

  // ==== BLE 상태 ====
  BluetoothDevice? picoDevice;
  BluetoothCharacteristic? qrChar;
  StreamSubscription<List<ScanResult>>? _scanSub;

  // ==== QR 카메라 ====
  final GlobalKey qrKey = GlobalKey(debugLabel: 'QR');
  QRViewController? qrController;

  // ==== UI 상태 ====
  String statusMessage = "서비스 UUID로 기기 검색 중...";
  String lastSent = "";
  bool get isConnected => qrChar != null;

  @override
  void initState() {
    super.initState();
    _scanAndConnectByService();
  }

  @override
  void dispose() {
    _scanSub?.cancel();
    qrController?.dispose();
    super.dispose();
  }

  // === 1) 서비스 UUID로 스캔 & 연결 ===
  Future<void> _scanAndConnectByService() async {
    setState(() => statusMessage = "서비스 UUID로 기기 검색 중...");

    try {
      // 기존 스캔이 있다면 중지
      await FlutterBluePlus.stopScan();
    } catch (_) {}

    // 서비스 UUID 필터 사용
    await FlutterBluePlus.startScan(
      withServices: [Guid(serviceUuid)],
      timeout: const Duration(seconds: 10),
    );

    _scanSub?.cancel();
    _scanSub = FlutterBluePlus.scanResults.listen((results) async {
      for (final r in results) {
        final adv = r.advertisementData;
        // 필터로 이미 제한되지만, 한 번 더 확인(안전)
        final hasSvc = adv.serviceUuids.contains(Guid(serviceUuid));
        if (!hasSvc) continue;

        // 매치되면 즉시 스캔 중단 & 연결 시도
        await FlutterBluePlus.stopScan();
        await _scanSub?.cancel();

        picoDevice = r.device;
        final shownName =
            adv.localName.isNotEmpty ? adv.localName : (r.device.platformName.isNotEmpty ? r.device.platformName : targetName);

        setState(() => statusMessage = "연결 중... ($shownName)");
        try {
          // 혹시 이전 세션이 있으면 정리
          try {
            await picoDevice!.disconnect();
          } catch (_) {}

          await picoDevice!.connect(timeout: const Duration(seconds: 8));
          await _discoverAndPickWritableCharacteristic();

          if (qrChar != null) {
            setState(() => statusMessage = "기기 연결됨 – 카메라 준비됨");
          } else {
            setState(() => statusMessage = "연결됨 – 쓰기 특성 탐색 실패");
          }
        } catch (e) {
          setState(() => statusMessage = "연결 실패: $e");
        }
        break;
      }
    }, onDone: () {
      if (!isConnected && mounted) {
        setState(() => statusMessage = "기기 미발견 – 다시 시도하세요");
      }
    });
  }

  // === 2) 서비스/특성 탐색 (charUuid 우선, 없으면 write 가능한 아무 특성) ===
  Future<void> _discoverAndPickWritableCharacteristic() async {
    if (picoDevice == null) return;

    final services = await picoDevice!.discoverServices();
    BluetoothCharacteristic? found;

    // 1) 목표 서비스에서 먼저 찾기
    final targetService = services.firstWhere(
      (s) => s.uuid == Guid(serviceUuid),
      orElse: () => null as BluetoothService,
    );

    if (targetService != null && targetService.characteristics.isNotEmpty) {
      found = targetService.characteristics.firstWhere(
        (c) => c.uuid == Guid(charUuid),
        orElse: () {
          return targetService.characteristics.firstWhere(
            (c) => c.properties.write || c.properties.writeWithoutResponse,
            orElse: () => null as BluetoothCharacteristic,
          );
        },
      );
      if (found != null) {
        setState(() => statusMessage = "쓰기 특성 탐색 성공 (UUID 서비스 안에서 발견)");
      }
    }

    // 2) 목표 서비스 안에서 못 찾았으면 전체 서비스에서 fallback
    if (found == null) {
      for (final s in services) {
        for (final c in s.characteristics) {
          if (c.uuid == Guid(charUuid) ||
              c.properties.write ||
              c.properties.writeWithoutResponse) {
            found = c;
            break;
          }
        }
        if (found != null) break;
      }

      if (found != null) {
        setState(() => statusMessage = "쓰기 특성 탐색 성공 (Fallback에서 발견)");
      }
    }

    // 3) 최종 할당
    qrChar = found;

    // 4) 그래도 못 찾았으면 실패 메시지
    if (qrChar == null) {
      setState(() => statusMessage = "쓰기 특성 탐색 실패 ");
    }
  }

  // === 3) QR 읽으면 즉시 BLE로 전송 ===
  void _onQRViewCreated(QRViewController controller) {
    qrController = controller;

    controller.scannedDataStream.listen((scan) async {
      final code = scan.code ?? "";
      if (code.isEmpty || qrChar == null) return;
      if (code == lastSent) return; // 중복 전송 방지(간단)

      try {
        // Pico는 FLAG_WRITE만 있으니 response 방식으로 쓰기
        await qrChar!.write(utf8.encode(code), withoutResponse: false);
        setState(() {
          lastSent = code;
          statusMessage = "전송 완료 ($code)";
        });
      } catch (e) {
        setState(() => statusMessage = "전송 실패: $e");
      }
    });
  }

  // === 4) 액션 ===
  Future<void> _rescan() async {
    setState(() {
      statusMessage = "서비스 UUID로 기기 재검색 중...";
      qrChar = null;
      lastSent = "";
    });
    await _scanAndConnectByService();
  }

  Future<void> _disconnect() async {
    try {
      await _scanSub?.cancel();
      await FlutterBluePlus.stopScan();
    } catch (_) {}
    try {
      await picoDevice?.disconnect();
    } catch (_) {}
    setState(() {
      picoDevice = null;
      qrChar = null;
      statusMessage = "연결 해제됨";
    });
  }

  // === 5) UI ===
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("BLE QR Sender"),
        actions: [
          IconButton(
            onPressed: _rescan,
            icon: const Icon(Icons.refresh),
            tooltip: "Rescan",
          ),
          IconButton(
            onPressed: _disconnect,
            icon: const Icon(Icons.link_off),
            tooltip: "Disconnect",
          ),
        ],
      ),
      body: Stack(
        children: [
          // 연결되기 전에는 안내 화면, 연결되면 카메라 표시
          if (isConnected)
            QRView(
              key: qrKey,
              onQRViewCreated: _onQRViewCreated,
              overlay: QrScannerOverlayShape(
                borderRadius: 12,
                borderLength: 24,
                borderWidth: 8,
                cutOutSize: 260,
              ),
            )
          else
            Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.bluetooth_searching, size: 64),
                  const SizedBox(height: 12),
                  Text(
                    "Pico BLE 기기 탐색 중",
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    "필터: $serviceUuid",
                    style: Theme.of(context).textTheme.bodySmall,
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),

          // 상태 메시지 오버레이
          Positioned(
            left: 0,
            right: 0,
            bottom: 24,
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 16),
              padding: const EdgeInsets.all(12),
              color: Colors.black54,
              child: Text(
                statusMessage,
                style: const TextStyle(color: Colors.white, fontSize: 16),
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

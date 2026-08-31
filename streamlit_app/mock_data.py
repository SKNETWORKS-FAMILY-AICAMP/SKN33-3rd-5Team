"""Deterministic mock responses used before the sLLM and RAG are connected."""

from __future__ import annotations

from copy import deepcopy

from src.contracts.models import CONTRACT_VERSION


PRODUCTS = [
    {
        "name": "Raspberry Pi 5",
        "badge": "★ 가장 추천",
        "badge_tone": "primary",
        "image": "assets/media/images/products/raspberry-pi-5.jpg",
        "cpu": "2.4 GHz, 쿼드 코어 ARM",
        "memory": "4GB / 8GB",
        "wireless": "Wi-Fi 5, Bluetooth 5.0",
        "size": "85.6 × 56.5 mm",
        "performance": "매우 높음",
        "use_case": "홈 서버, 고성능 작업",
        "reason": "가정용 홈 서버에 최적",
        "limitations": ["안정적인 사용을 위해 27W USB-C 전원 공급장치가 권장됩니다.", "지속 부하에서는 능동 냉각을 권장합니다."],
        "url": "https://www.raspberrypi.com/products/raspberry-pi-5/",
    },
    {
        "name": "Raspberry Pi 4 Model B",
        "badge": "⚖ 균형 잡힌 선택",
        "badge_tone": "warm",
        "image": "assets/media/images/products/raspberry-pi-4-model-b.jpg",
        "cpu": "1.5 GHz, 쿼드 코어 ARM",
        "memory": "2GB / 4GB / 8GB",
        "wireless": "Wi-Fi 5, Bluetooth 5.0",
        "size": "85.6 × 56.5 mm",
        "performance": "높음",
        "use_case": "일반 서버, 미디어, 개발",
        "reason": "균형 잡힌 성능과 호환성",
        "limitations": ["모델과 메모리 용량을 먼저 확인하세요."],
        "url": "https://www.raspberrypi.com/products/raspberry-pi-4-model-b/",
    },
    {
        "name": "Raspberry Pi Zero 2 W",
        "badge": "❀ 가벼운 작업",
        "badge_tone": "green",
        "image": "assets/media/images/products/raspberry-pi-zero-2-w.jpg",
        "cpu": "1.0 GHz, 쿼드 코어 ARM",
        "memory": "512MB",
        "wireless": "Wi-Fi 4, Bluetooth 4.2",
        "size": "65.0 × 30.0 mm",
        "performance": "보통",
        "use_case": "경량 서버, IoT, 자동화",
        "reason": "가벼운 서버와 IoT 프로젝트",
        "limitations": ["메모리가 512MB이므로 고부하 서비스에는 적합하지 않습니다."],
        "url": "https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/",
    },
]


RECOMMENDATION_SOURCES = [
    {
        "title": "Raspberry Pi computer hardware",
        "section": "Raspberry Pi 5 and Raspberry Pi 4 Model B",
        "url": "https://www.raspberrypi.com/documentation/computers/raspberry-pi.html",
        "license": "CC BY-SA 4.0",
    },
    {
        "title": "Raspberry Pi Zero 2 W",
        "section": "Product overview",
        "url": "https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/",
        "license": "Official product page",
    },
]


BOOT_RESPONSE = {
    "status": "answered",
    "label": "공식 문서에서 확인한 답변",
    "title": "먼저 확인하세요",
    "intro": "Raspberry Pi 5가 부팅되지 않는다면 전원, OS 이미지, 상태 LED를 순서대로 확인해 보세요. [C1] [C2]",
    "steps": ["전원 연결과 권장 전원 장치 확인", "Raspberry Pi Imager로 OS 이미지 다시 기록", "상태 LED 점멸 패턴 확인"],
    "warning": "문제가 계속되면 사용 중인 전원 장치와 LED 점멸 패턴을 알려주세요.",
    "conditions": {
        "schema_version": CONTRACT_VERSION,
        "intent": "troubleshooting",
        "use_case": None,
        "product_models": ["Raspberry Pi 5"],
        "os_versions": ["Raspberry Pi OS"],
        "task": "troubleshooting",
        "performance_priority": None,
        "wireless_required": None,
        "camera_required": None,
        "gpio_required": None,
        "monitor_available": None,
        "remote_access_required": None,
        "user_level": None,
        "needs_clarification": False,
        "clarification_questions": [],
    },
    "sources": [
        {"citation_id": "C1", "title": "Getting started", "section": "Troubleshooting", "url": "https://www.raspberrypi.com/documentation/computers/getting-started.html#troubleshooting", "license": "CC BY-SA 4.0"},
        {"citation_id": "C2", "title": "LED warning flash codes", "section": "LED warning flash codes", "url": "https://www.raspberrypi.com/documentation/computers/configuration.html#led-warning-flash-codes", "license": "CC BY-SA 4.0"},
    ],
    "related": ["SD 카드 OS 다시 설치", "LED 점멸 코드", "공식 지원 문의"],
}


def recommendation_conditions(
    purpose: str,
    user_level: str,
    performance: str,
    wifi: bool,
    camera: bool,
    gpio: bool,
    monitor_absent: bool,
) -> dict:
    """Return a canonical-looking mock condition payload from the form."""

    use_case = "home_server"
    task = "server_operation"
    lowered = purpose.lower()
    if "카메라" in lowered or "관찰" in lowered:
        use_case, task = "camera_monitoring", "camera_setup"
    elif "센서" in lowered or "스마트팜" in lowered:
        use_case, task = "smart_farm_monitoring", "sensor_monitoring"
    elif "코딩" in lowered or "교육" in lowered:
        use_case, task = "education_coding", "desktop_programming"

    return {
        "schema_version": CONTRACT_VERSION,
        "intent": "product_recommendation",
        "use_case": use_case,
        "product_models": None,
        "os_versions": None,
        "task": task,
        "performance_priority": {"낮음": "low", "보통": "medium", "높음": "high"}[performance],
        "wireless_required": wifi,
        "camera_required": camera,
        "gpio_required": gpio,
        "monitor_available": not monitor_absent,
        "remote_access_required": monitor_absent,
        "user_level": {"입문자": "beginner", "중급자": "intermediate", "고급자": "advanced"}[user_level],
        "needs_clarification": False,
        "clarification_questions": [],
    }


def mock_qa_response(question: str) -> dict:
    """Select a safe deterministic response for common demo questions."""

    lowered = question.lower()
    response = deepcopy(BOOT_RESPONSE)
    if any(word in lowered for word in ("가격", "재고", "쇼핑몰")):
        response.update(
            status="out_of_scope",
            label="지원 범위 밖 질문",
            title="실시간 가격과 재고는 안내할 수 없어요",
            intro="PiCare는 공식 기술 문서를 근거로 답변하며, 실시간 판매 가격과 재고는 지원하지 않습니다.",
            steps=[], warning="제품 사양·설치·문제 해결에 관한 질문을 남겨 주세요.", sources=[], related=["홈 서버용 제품 추천", "Raspberry Pi 4와 5 비교", "공식 제품 사양"],
        )
        response["conditions"]["intent"] = "out_of_scope"
        response["conditions"]["product_models"] = ["Raspberry Pi 5"] if "5" in question else None
        return response

    if any(word in lowered for word in ("이전 지시", "출처를 만들", "오버클럭")):
        response.update(
            status="safety_blocked",
            label="안전 규칙에 따라 답변 보류",
            title="근거나 출처를 만들어 낼 수 없어요",
            intro="검색된 공식 문서에서 확인되지 않은 절차나 출처는 제공하지 않습니다.",
            steps=[], warning="공식 범위의 설치·환경 설정 질문으로 바꿔 물어보세요.", sources=[], related=["공식 설정 문서", "안전한 전원 사용", "지원 범위 확인"],
        )
        response["conditions"]["intent"] = "out_of_scope"
        return response

    if "ssh" in lowered or "원격" in lowered:
        response.update(
            title="SSH를 켜고 네트워크 정보를 확인하세요",
            intro="Raspberry Pi Imager의 OS 사용자 정의 메뉴에서 Wi-Fi와 SSH를 미리 설정하면 모니터 없이 첫 부팅부터 접속할 수 있습니다. [C1]",
            steps=["Imager에서 기기와 OS 선택", "OS 사용자 정의에서 호스트명·Wi-Fi·SSH 설정", "부팅 후 같은 네트워크에서 SSH 접속"],
            warning="비밀번호 인증을 쓰는 경우 강한 비밀번호를 설정하세요.",
            sources=[{"citation_id": "C1", "title": "Remote access", "section": "SSH", "url": "https://www.raspberrypi.com/documentation/computers/remote-access.html#ssh", "license": "CC BY-SA 4.0"}],
            related=["Imager에서 Wi-Fi 설정", "Raspberry Pi Connect", "SSH 키 인증"],
        )
        response["conditions"].update(intent="how_to", use_case="headless_remote_management", task="remote_access", remote_access_required=True)
        return response

    if "카메라" in lowered or "camera" in lowered:
        response.update(
            title="전원을 끄고 카메라 케이블부터 확인하세요",
            intro="카메라가 감지되지 않으면 보드에 맞는 케이블 방향과 연결 상태를 먼저 확인하고, 최신 Raspberry Pi OS에서 rpicam-apps로 테스트하세요. [C1] [C2]",
            steps=["전원을 끈 뒤 케이블 방향과 커넥터 잠금 확인", "Raspberry Pi OS 최신 패키지 확인", "rpicam-hello로 카메라 작동 테스트"],
            warning="전원이 켜진 상태에서 카메라 케이블을 연결하거나 분리하지 마세요.",
            sources=[
                {"citation_id": "C1", "title": "Camera hardware", "section": "Install a Raspberry Pi camera", "url": "https://www.raspberrypi.com/documentation/accessories/camera.html#install-a-raspberry-pi-camera", "license": "CC BY-SA 4.0"},
                {"citation_id": "C2", "title": "Camera software", "section": "rpicam-apps", "url": "https://www.raspberrypi.com/documentation/computers/camera_software.html", "license": "CC BY-SA 4.0"},
            ],
            related=["카메라 케이블 연결", "rpicam-hello 사용법", "Camera Module 3 설정"],
        )
        response["conditions"].update(intent="troubleshooting", use_case="camera_monitoring", task="troubleshooting", camera_required=True)
        return response

    if "부팅" in lowered and not any(token in lowered for token in ("pi 4", "pi 5", "raspberry pi 4", "raspberry pi 5")):
        response.update(
            status="needs_clarification",
            label="추가 정보가 필요해요",
            title="모델과 상태를 조금 더 알려주세요",
            intro="부팅 문제는 모델·OS·LED 패턴에 따라 확인 절차가 달라집니다.",
            steps=["사용 중인 Raspberry Pi 모델은 무엇인가요?", "Raspberry Pi OS 버전과 저장장치는 무엇인가요?", "상태 LED가 어떤 패턴으로 깜빡이나요?"],
            warning="확인되지 않은 원인을 추측하지 않습니다.", sources=[], related=["Raspberry Pi 5 부팅 문제", "LED 점멸 코드", "OS 이미지 다시 기록"],
        )
        response["conditions"].update(product_models=None, os_versions=None, needs_clarification=True, clarification_questions=response["steps"])
        return response

    return response

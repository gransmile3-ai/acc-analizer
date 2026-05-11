#!/usr/bin/env python3
"""
Assetto Corsa 분석기 - LMM 연동

역할:
1. C#에서 출력한 데이터 (JSON/UDP/CSV) 수신
2. 실시간 주행 데이터 분석
3. 성능 개선을 위한 피드백 생성
4. LMM에 분석 결과 전달

사용 명령:
  python analyze.py

요구 사항:
  - Python 3.8 이상
  - C# 프로그램 (acc.cs)가 실행 중이어야 함
"""

import json
import csv
import socket
import threading
import time
import logging
import requests
from collections import defaultdict
from pathlib import Path
from datetime import datetime
import statistics

# ═══════════════════════════════════════════════════════════════════════════════
# 1번: 전역 설정
# ═══════════════════════════════════════════════════════════════════════════════
# 이 섹션은 프로그램의 모든 설정을 중앙에서 관리합니다.
# 사용자가 여기서만 수정하면 전체 프로그램이 자동으로 조정됩니다.

# ─────────────────────────────────────────────────────────────────────────────
# 1-1: 데이터 파일 설정
# ─────────────────────────────────────────────────────────────────────────────
# C# 프로그램(acc.exe)에서 출력하는 파일들의 경로입니다.
# 상대 경로로 설정하면 프로그램이 있는 디렉토리를 기준으로 찾습니다.

# JSON: 최신 데이터 (100ms마다 업데이트, 항상 최신 상태)
JSON_FILE = "ac_telemetry.json"

# CSV: 전체 히스토리 (100ms마다 한 줄 추가, 세션 종료 후 분석용)
CSV_FILE = "ac_telemetry.csv"

# ─────────────────────────────────────────────────────────────────────────────
# 1-2: UDP 수신 설정
# ─────────────────────────────────────────────────────────────────────────────
# C#에서 UDP로 실시간 데이터를 전송하는 주소와 포트입니다.
# 이 리스너를 켜면 네트워크를 통해 다른 PC의 C# 프로그램과도 연동 가능합니다.

UDP_HOST = "127.0.0.1"  # localhost (같은 PC에서만 수신)
UDP_PORT = 5005         # C#에서 설정한 포트와 동일해야 함

# UDP 수신 타임아웃 (초)
UDP_TIMEOUT = 1.0

# ─────────────────────────────────────────────────────────────────────────────
# 1-3: LMM 통신 설정
# ─────────────────────────────────────────────────────────────────────────────
# LMM(LMU Manager/대시보드)과 통신할 주소입니다.
# LMM이 실행 중이면 자동으로 분석 결과를 전달합니다.

LMM_ENABLED = True              # LMM 통신 활성화/비활성화
LMM_HOST = "127.0.0.1"         # LMM 호스트 (같은 PC)
LMM_PORT = 5006                 # LMM API 포트 (기본값)
LMM_TIMEOUT = 2.0              # LMM 통신 타임아웃 (초)

# LMM 통신 방식 선택
# "http": HTTP API (권장, 안정적)
# "tcp": TCP 소켓 (빠름)
# "udp": UDP (일방향 전송)
LMM_PROTOCOL = "http"

# ─────────────────────────────────────────────────────────────────────────────
# 1-4: 분석 설정
# ─────────────────────────────────────────────────────────────────────────────
# 실시간 분석의 주기와 민감도를 조정합니다.

# 피드백 생성 주기 (초)
FEEDBACK_INTERVAL = 3.0

# 데이터 폴링 주기 (초) - JSON 파일을 얼마나 자주 확인할지
POLL_INTERVAL = 0.5

# 타이어 온도 최적 범위 (°C)
TYRE_OPTIMAL_MIN = 60
TYRE_OPTIMAL_MAX = 100
TYRE_OVERHEAT_THRESHOLD = 110
TYRE_UNDERHEAT_THRESHOLD = 40

# 타이어 온도 불균형 임계값 (°C)
TYRE_VARIANCE_THRESHOLD = 15

# 브레이크 온도 최적 범위 (°C)
BRAKE_OPTIMAL_MIN = 200
BRAKE_OPTIMAL_MAX = 400
BRAKE_OVERHEAT_THRESHOLD = 500
BRAKE_UNDERHEAT_THRESHOLD = 150

# 랩 타임 개선 감지 임계값 (밀리초)
LAP_IMPROVEMENT_THRESHOLD = 100  # 100ms 이상 단축되면 개선으로 판정

# 연료 부족 경고 임계값 (예상 랩 수 비율)
FUEL_WARNING_RATIO = 0.9  # 남은 랩 수의 90% 미만이면 경고

# ─────────────────────────────────────────────────────────────────────────────
# 1-5: 출력 및 로깅 설정
# ─────────────────────────────────────────────────────────────────────────────

# 로그 파일 경로 (분석 결과 기록)
LOG_FILE = "ac_analysis.log"

# 디버그 모드 (상세 출력 활성화)
DEBUG_MODE = False

# 콘솔에 출력할 피드백 최대 개수
MAX_FEEDBACK_DISPLAY = 5

# ─────────────────────────────────────────────────────────────────────────────
# 1-6: 성능 및 최적화 설정
# ─────────────────────────────────────────────────────────────────────────────

# 메모리 히스토리 크기 (최근 몇 개의 데이터만 메모리에 유지)
MAX_HISTORY_SIZE = 100

# 멀티스레딩 활성화 (UDP 수신을 별도 스레드에서 처리)
USE_THREADING = True

# ─────────────────────────────────────────────────────────────────────────────
# 1-7: 경로 정규화 (자동)
# ─────────────────────────────────────────────────────────────────────────────
# 상대 경로를 절대 경로로 변환하여 어디서 실행해도 파일을 찾을 수 있게 함

from pathlib import Path

# 현재 스크립트가 있는 디렉토리를 기준으로 경로 설정
SCRIPT_DIR = Path(__file__).parent

# JSON/CSV 파일의 절대 경로
JSON_FILE = SCRIPT_DIR / JSON_FILE
CSV_FILE = SCRIPT_DIR / CSV_FILE
LOG_FILE = SCRIPT_DIR / LOG_FILE


# ═══════════════════════════════════════════════════════════════════════════════
# 1-8: 로깅 초기화 (자동)
# ═══════════════════════════════════════════════════════════════════════════════
# 모든 분석 결과와 오류를 파일에 기록합니다.
# 나중에 문제가 발생했을 때 원인 분석에 유용합니다.

# 로깅 포맷: [시간] [레벨] 메시지
logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        # 파일에 기록
        logging.FileHandler(str(LOG_FILE)),
        # 콘솔에도 출력
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1-9: 설정 검증 함수
# ═══════════════════════════════════════════════════════════════════════════════
# 프로그램 시작 시 설정이 올바른지 확인하는 함수입니다.
# 파일 경로, 포트 범위, 설정값 등을 검증합니다.

def validate_config():
    """
    설정이 유효한지 확인
    
    검사 항목:
    - 파일 경로 접근 가능성
    - 포트 번호 범위 (0-65535)
    - 온도 임계값 논리 (최소 < 최적 < 최대)
    - 시간 값 양수
    """
    errors = []
    warnings = []
    
    # 1. 파일 경로 검증
    if not JSON_FILE.parent.exists():
        errors.append(f"JSON 디렉토리 없음: {JSON_FILE.parent}")
    
    # 2. 포트 번호 범위 검증
    if not (0 < UDP_PORT < 65535):
        errors.append(f"UDP 포트 범위 오류: {UDP_PORT} (1-65534)")
    
    if LMM_ENABLED and not (0 < LMM_PORT < 65535):
        errors.append(f"LMM 포트 범위 오류: {LMM_PORT}")
    
    # 3. 온도 설정 논리 검증
    if TYRE_OPTIMAL_MIN >= TYRE_OPTIMAL_MAX:
        errors.append(f"타이어 온도 설정 오류: 최소({TYRE_OPTIMAL_MIN}) >= 최대({TYRE_OPTIMAL_MAX})")
    
    if BRAKE_OPTIMAL_MIN >= BRAKE_OPTIMAL_MAX:
        errors.append(f"브레이크 온도 설정 오류: 최소({BRAKE_OPTIMAL_MIN}) >= 최대({BRAKE_OPTIMAL_MAX})")
    
    # 4. 피드백 주기 검증
    if FEEDBACK_INTERVAL <= 0 or POLL_INTERVAL <= 0:
        errors.append("피드백/폴링 주기는 0보다 커야 함")
    
    # 5. 경고 (치명적이지 않음)
    if not (TYRE_OPTIMAL_MIN < TYRE_UNDERHEAT_THRESHOLD < TYRE_OPTIMAL_MAX):
        warnings.append(f"타이어 저온 임계값({TYRE_UNDERHEAT_THRESHOLD})이 최적 범위({TYRE_OPTIMAL_MIN}-{TYRE_OPTIMAL_MAX}) 내에 없음")
    
    # 에러 출력
    if errors:
        logger.error("설정 검증 실패:")
        for error in errors:
            logger.error(f"  ❌ {error}")
        return False
    
    # 경고 출력
    if warnings:
        logger.warning("설정 경고:")
        for warning in warnings:
            logger.warning(f"  ⚠️  {warning}")
    
    logger.info("✅ 설정 검증 완료")
    return True


def print_config():
    """
    현재 설정을 보기 좋게 출력
    """
    logger.info("\n" + "="*70)
    logger.info("📋 프로그램 설정")
    logger.info("="*70)
    logger.info(f"  JSON 파일: {JSON_FILE}")
    logger.info(f"  CSV 파일: {CSV_FILE}")
    logger.info(f"  로그 파일: {LOG_FILE}")
    logger.info(f"\n  UDP 수신: {UDP_HOST}:{UDP_PORT}")
    logger.info(f"  LMM 통신: {('활성화' if LMM_ENABLED else '비활성화')} - {LMM_HOST}:{LMM_PORT} ({LMM_PROTOCOL.upper()})")
    logger.info(f"\n  분석 주기: {FEEDBACK_INTERVAL}초")
    logger.info(f"  폴링 주기: {POLL_INTERVAL}초")
    logger.info(f"  디버그 모드: {'ON' if DEBUG_MODE else 'OFF'}")
    logger.info("="*70 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# 2번: 데이터 수집 클래스
# ═══════════════════════════════════════════════════════════════════════════════

class DataCollector:
    """
    C#에서 출력한 데이터를 수집하는 클래스
    - JSON 파일에서 최신 데이터 읽기 (폴링)
    - UDP로 실시간 데이터 수신
    - CSV 파일에서 히스토리 읽기
    """
    
    def __init__(self):
        self.current_data = None
        self.lap_history = []
        self.running = False
    
    def read_json(self):
        """JSON 파일에서 최신 데이터 읽기"""
        try:
            if Path(JSON_FILE).exists():
                with open(JSON_FILE, 'r') as f:
                    data = json.load(f)
                    self.current_data = data
                    logger.debug(f"JSON 로드 성공: {JSON_FILE}")
                return self.current_data
        except Exception as e:
            logger.debug(f"JSON 읽기 오류: {e}")
        return None
    
    def read_csv(self):
        """CSV 파일에서 히스토리 데이터 읽기"""
        try:
            if Path(CSV_FILE).exists():
                with open(CSV_FILE, 'r') as f:
                    reader = csv.DictReader(f)
                    self.lap_history = list(reader)
                logger.debug(f"CSV 로드: {len(self.lap_history)} 행")
                return self.lap_history
        except Exception as e:
            logger.error(f"CSV 읽기 오류: {e}")
        return None
    
    def listen_udp(self):
        """UDP로 실시간 데이터 수신 (비동기)"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((UDP_HOST, UDP_PORT))
            sock.settimeout(UDP_TIMEOUT)
            logger.info(f"✅ UDP 리스너 준비: {UDP_HOST}:{UDP_PORT}")
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(65535)
                    self.current_data = json.loads(data.decode('utf-8'))
                    logger.debug(f"UDP 수신: {len(data)} bytes from {addr}")
                except socket.timeout:
                    pass
                except Exception as e:
                    logger.debug(f"UDP 수신 오류: {e}")
            
            sock.close()
        except Exception as e:
            logger.error(f"UDP 바인드 오류: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 3번: 실시간 성능 분석 클래스
# ═══════════════════════════════════════════════════════════════════════════════

class PerformanceAnalyzer:
    """
    실시간 주행 데이터를 분석해서 성능 개선 제안을 제공
    
    분석 항목:
    1. 랩 타임 추적 - 현재 랩 vs 베스트 랩
    2. 타이어 온도 - 최적 범위 확인
    3. 브레이크 온도 - 과열 여부 감지
    4. 속도 최적화 - 코너별 진출/진입 속도
    5. 연료 효율 - 주행 중 연료 소비량
    """
    
    def __init__(self):
        self.best_lap_time = None
        self.current_lap_time = None
        self.session_data = []
        self.feedback = []
    
    def analyze_lap(self, data):
        """
        현재 랩 타임 분석
        - 현재 랩과 베스트 랩 비교
        - 델타 타임 계산
        - 피드백 생성
        """
        if not data or 'RealtimeData' not in data:
            return
        
        rt = data['RealtimeData']
        
        # 시간 문자열 파싱 (예: "1:23.456")
        try:
            current = self._parse_time(rt.get('CurrentTime', ''))
            last = self._parse_time(rt.get('LastTime', ''))
            best = self._parse_time(rt.get('BestTime', ''))
            
            if best and best > 0:
                self.best_lap_time = best
            
            if current and current > 0:
                self.current_lap_time = current
            
            # 피드백 생성
            if self.best_lap_time and self.current_lap_time:
                delta = self.current_lap_time - self.best_lap_time
                if delta < 0:
                    self.feedback.append(f"🎯 PB! {abs(delta):.3f}초 단축!")
                elif delta > 0 and delta < 1000:  # 1초 이내
                    self.feedback.append(f"⚡ 거의 근접! +{delta/1000:.3f}초")
        except:
            pass
    
    def analyze_tyres(self, data):
        """
        타이어 온도 분석
        - 최적 온도 범위: 60-100°C
        - 과열 경고: >110°C
        - 저온 경고: <40°C
        """
        if not data or 'RealtimeData' not in data:
            return
        
        rt = data['RealtimeData']
        tyres = rt.get('TyreCoreTemperature', [])
        
        if len(tyres) < 4:
            return
        
        avg_temp = sum(tyres) / 4
        max_temp = max(tyres)
        min_temp = min(tyres)
        
        # 온도별 상태 판정
        if max_temp > 110:
            self.feedback.append(f"⚠️  타이어 과열: {max_temp:.1f}°C (스로틀 줄이기)")
        elif max_temp < 40:
            self.feedback.append(f"❄️  타이어 냉각: {max_temp:.1f}°C (워밍업 필요)")
        elif 60 <= avg_temp <= 100:
            self.feedback.append(f"✅ 타이어 최적: {avg_temp:.1f}°C (현재 좋은 상태)")
        
        # 타이어 불균형 감지
        temp_variance = max_temp - min_temp
        if temp_variance > 15:
            self.feedback.append(f"⚙️  타이어 불균형: 온도차 {temp_variance:.1f}°C (세팅 확인)")
    
    def analyze_brakes(self, data):
        """
        브레이크 온도 분석
        - 최적 온도 범위: 200-400°C
        - 과열 경고: >500°C
        - 빈약함: <150°C
        """
        if not data or 'RealtimeData' not in data:
            return
        
        rt = data['RealtimeData']
        brakes = rt.get('BrakeTemp', [])
        
        if len(brakes) < 4:
            return
        
        avg_brake_temp = sum(brakes) / 4
        max_brake_temp = max(brakes)
        
        if max_brake_temp > 500:
            self.feedback.append(f"🔥 브레이크 과열: {max_brake_temp:.1f}°C (초반부 페이싱 조절)")
        elif max_brake_temp < 150:
            self.feedback.append(f"❓ 브레이크 미활용: {max_brake_temp:.1f}°C (더 강하게 제동)")
        elif 200 <= avg_brake_temp <= 400:
            self.feedback.append(f"✅ 브레이크 최적: {avg_brake_temp:.1f}°C")
    
    def analyze_speed(self, data):
        """
        속도 분석
        - 현재 속도와 최고 속도 비교
        - 코너 진입/진출 속도 최적화 제안
        """
        if not data or 'RealtimeData' not in data:
            return
        
        rt = data['RealtimeData']
        speed = rt.get('SpeedKmh', 0)
        
        # 속도별 코너 유형 판정 (가상)
        if 0 < speed < 80:
            self.feedback.append(f"🔄 저속 코너: {speed:.1f} km/h (더 빨리 빠져나가기)")
        elif 80 <= speed < 150:
            self.feedback.append(f"⏱️  중속: {speed:.1f} km/h")
        elif speed >= 150:
            self.feedback.append(f"🚀 고속: {speed:.1f} km/h (스로틀 제어)")
    
    def analyze_fuel(self, data):
        """
        연료 효율 분석
        - 현재 연료량과 남은 랩 수 비교
        - 연료 세이브 필요 여부 판정
        """
        if not data or 'RealtimeData' not in data:
            return
        
        rt = data['RealtimeData']
        fuel = rt.get('Fuel', 0)
        est_laps = rt.get('FuelEstimatedLaps', 0)
        total_laps = rt.get('NumberOfLaps', 0)
        completed_laps = rt.get('CompletedLaps', 0)
        
        remaining_laps = total_laps - completed_laps
        
        if est_laps > 0:
            if est_laps < remaining_laps * 0.9:
                self.feedback.append(f"⛽ 연료 부족: {fuel:.1f}L (페이싱 늘리기, 예상 {est_laps:.1f} 랩)")
            elif est_laps > remaining_laps * 1.2:
                self.feedback.append(f"✅ 연료 충분: {fuel:.1f}L (공격적으로 주행 가능)")
    
    def get_feedback(self, data):
        """
        모든 분석을 수행하고 피드백 반환
        """
        self.feedback = []
        
        self.analyze_lap(data)
        self.analyze_tyres(data)
        self.analyze_brakes(data)
        self.analyze_speed(data)
        self.analyze_fuel(data)
        
        return self.feedback
    
    def _parse_time(self, time_str):
        """
        시간 문자열 파싱: "1:23.456" → 83456 (밀리초)
        """
        try:
            if not time_str or time_str == "--.--":
                return 0
            parts = time_str.split(':')
            minutes = int(parts[0])
            sec_parts = parts[1].split('.')
            seconds = int(sec_parts[0])
            ms = int(sec_parts[1])
            return minutes * 60000 + seconds * 1000 + ms
        except:
            return 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4번: 세션 통계 분석 클래스
# ═══════════════════════════════════════════════════════════════════════════════

class SessionAnalytics:
    """
    세션 전체의 통계를 분석해서 진행도와 개선도를 추적
    
    추적 항목:
    - 랩 타임 추세 (개선/악화)
    - 평균 속도
    - 타이어/브레이크 마모도
    - 연료 소비량
    - 순위 변화
    """
    
    def __init__(self):
        self.lap_times = []
        self.avg_speeds = []
        self.positions = []
    
    def load_csv_history(self, csv_file):
        """CSV 파일에서 히스토리 로드"""
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        self.lap_times.append(float(row.get('CurrentTime', 0)) if row.get('CurrentTime') else 0)
                        self.avg_speeds.append(float(row.get('Speed', 0)))
                        self.positions.append(int(row.get('Position', 0)))
                    except (ValueError, KeyError):
                        continue
            logger.debug(f"히스토리 로드: {len(self.lap_times)} 데이터 포인트")
        except Exception as e:
            logger.error(f"CSV 히스토리 로드 오류: {e}")
    
    def get_statistics(self):
        """통계 계산"""
        stats = {}
        
        if self.lap_times:
            stats['avg_lap_time'] = statistics.mean(self.lap_times)
            stats['best_lap_time'] = min(self.lap_times)
            stats['worst_lap_time'] = max(self.lap_times)
        
        if self.avg_speeds:
            stats['avg_speed'] = statistics.mean(self.avg_speeds)
            stats['max_speed'] = max(self.avg_speeds)
        
        if self.positions:
            stats['best_position'] = min(self.positions)
            stats['current_position'] = self.positions[-1] if self.positions else 0
        
        return stats
    
    def get_trend(self):
        """
        랩 타임 추세 분석
        - 개선 중: 랩 타임이 줄어들고 있음
        - 악화 중: 랩 타임이 늘어나고 있음
        - 안정적: 일정한 속도 유지
        """
        if len(self.lap_times) < 3:
            return "데이터 부족"
        
        recent = self.lap_times[-3:]
        trend = recent[-1] - recent[0]
        
        if trend < -100:  # 100ms 이상 단축
            return "📈 개선 중 (빠르고 있음)"
        elif trend > 100:
            return "📉 악화 중 (느려지고 있음)"
        else:
            return "📊 안정적 (일정한 페이싱)"


# ═══════════════════════════════════════════════════════════════════════════════
# 5번: LMM 통신 클래스 (구현)
# ═══════════════════════════════════════════════════════════════════════════════

class LMMCommunicator:
    """
    LMM과 통신해서 분석 결과를 전달하는 클래스
    
    지원 프로토콜:
    1. HTTP: RESTful API를 통한 통신 (권장)
    2. TCP: 소켓 기반 직접 통신 (빠름)
    3. UDP: 일방향 전송 (간단함)
    """
    
    def __init__(self, host, port, protocol='http'):
        self.host = host
        self.port = port
        self.protocol = protocol.lower()
        self.connected = False
        self.session = None
        
        if self.protocol == 'http':
            self.session = requests.Session()
            self.url = f"http://{host}:{port}/api/feedback"
        
        logger.info(f"LMM 통신기 초기화: {protocol.upper()} {host}:{port}")
    
    def connect(self):
        """
        LMM에 연결 시도
        - HTTP: URL 접근 가능성 확인
        - TCP: 소켓 연결 테스트
        """
        try:
            if self.protocol == 'http':
                response = self.session.get(
                    f"http://{self.host}:{self.port}/api/health",
                    timeout=LMM_TIMEOUT
                )
                self.connected = response.status_code == 200
                if self.connected:
                    logger.info("✅ LMM HTTP 연결 성공")
                else:
                    logger.warning(f"LMM 응답 오류: {response.status_code}")
            
            elif self.protocol == 'tcp':
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(LMM_TIMEOUT)
                sock.connect((self.host, self.port))
                sock.close()
                self.connected = True
                logger.info("✅ LMM TCP 연결 성공")
            
        except Exception as e:
            logger.warning(f"LMM 연결 실패: {e} (오프라인 모드 진행)")
            self.connected = False
    
    def send_feedback(self, feedback_list, session_data=None):
        """
        피드백을 LMM에 전송
        
        Args:
            feedback_list: 피드백 문자열 리스트
            session_data: 세션 통계 딕셔너리 (선택사항)
        
        Returns:
            bool: 전송 성공 여부
        """
        if not LMM_ENABLED:
            return False
        
        if not self.connected:
            # 오프라인 모드: 콘솔 출력만 수행
            self._print_feedback(feedback_list)
            return False
        
        try:
            if self.protocol == 'http':
                return self._send_http(feedback_list, session_data)
            elif self.protocol == 'tcp':
                return self._send_tcp(feedback_list, session_data)
            elif self.protocol == 'udp':
                return self._send_udp(feedback_list, session_data)
        except Exception as e:
            logger.error(f"피드백 전송 오류: {e}")
            return False
    
    def _send_http(self, feedback_list, session_data):
        """
        HTTP API를 통해 LMM에 피드백 전송
        
        API 형식:
          POST /api/feedback
          {
            "timestamp": "2026-05-11T12:34:56",
            "feedbacks": ["피드백1", "피드백2", ...],
            "session": { "avg_speed": 185.2, "best_lap": 83450, ... }
          }
        """
        try:
            payload = {
                "timestamp": datetime.now().isoformat(),
                "feedbacks": feedback_list[:MAX_FEEDBACK_DISPLAY],
                "session": session_data or {}
            }
            
            response = self.session.post(
                self.url,
                json=payload,
                timeout=LMM_TIMEOUT
            )
            
            if response.status_code == 200:
                logger.debug(f"✅ LMM HTTP 전송 성공 ({len(feedback_list)} 피드백)")
                return True
            else:
                logger.warning(f"LMM HTTP 응답 오류: {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"HTTP 전송 실패: {e}")
            return False
    
    def _send_tcp(self, feedback_list, session_data):
        """
        TCP 소켓을 통해 LMM에 피드백 전송 (더 빠름)
        
        메시지 형식:
          JSON 문자열 + null terminator
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(LMM_TIMEOUT)
            sock.connect((self.host, self.port))
            
            message = {
                "type": "feedback",
                "timestamp": datetime.now().isoformat(),
                "feedbacks": feedback_list[:MAX_FEEDBACK_DISPLAY],
                "session": session_data or {}
            }
            
            data = json.dumps(message).encode('utf-8') + b'\0'
            sock.sendall(data)
            sock.close()
            
            logger.debug(f"✅ LMM TCP 전송 성공")
            return True
        
        except Exception as e:
            logger.error(f"TCP 전송 실패: {e}")
            return False
    
    def _send_udp(self, feedback_list, session_data):
        """
        UDP를 통해 LMM에 피드백 전송 (일방향, 가장 빠름)
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            message = {
                "type": "feedback",
                "timestamp": datetime.now().isoformat(),
                "feedbacks": feedback_list[:MAX_FEEDBACK_DISPLAY],
                "session": session_data or {}
            }
            
            data = json.dumps(message).encode('utf-8')
            sock.sendto(data, (self.host, self.port))
            sock.close()
            
            logger.debug(f"✅ LMM UDP 전송 성공")
            return True
        
        except Exception as e:
            logger.error(f"UDP 전송 실패: {e}")
            return False
    
    def _print_feedback(self, feedback_list):
        """
        LMM 연결 불가능할 때 콘솔에 출력 (오프라인 모드)
        """
        if not feedback_list:
            return
        
        print("\n" + "="*70)
        print("🎮 분석 피드백 (LMM 오프라인)")
        print("="*70)
        for fb in feedback_list[:MAX_FEEDBACK_DISPLAY]:
            print(f"  {fb}")
        print("="*70 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# 6번: 메인 루프
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """
    메인 분석 루프
    
    순서:
    1. 설정 검증
    2. 데이터 수집 초기화
    3. LMM 연결 시도
    4. 데이터 분석 루프
    5. 피드백 생성 및 LMM 전송
    6. 세션 종료 시 최종 통계 출력
    """
    
    # ─────────────────────────────────────────────────────────────────────────
    # 1단계: 초기화
    # ─────────────────────────────────────────────────────────────────────────
    
    print_config()  # 설정 출력
    
    if not validate_config():  # 설정 검증
        logger.error("설정 검증 실패. 프로그램 종료.")
        return
    
    logger.info("🏁 Assetto Corsa 분석기 시작...")
    
    # 분석 엔진 초기화
    collector = DataCollector()
    analyzer = PerformanceAnalyzer()
    session = SessionAnalytics()
    
    # LMM 통신 초기화
    lmm = LMMCommunicator(LMM_HOST, LMM_PORT, LMM_PROTOCOL)
    if LMM_ENABLED:
        lmm.connect()  # LMM 연결 시도 (실패해도 계속 진행)
    
    # ─────────────────────────────────────────────────────────────────────────
    # 2단계: 데이터 로드
    # ─────────────────────────────────────────────────────────────────────────
    
    logger.info("기존 데이터 로드 중...")
    collector.read_csv()
    session.load_csv_history(str(CSV_FILE))
    logger.info(f"✅ {len(collector.lap_history)} 행의 히스토리 로드 완료")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 3단계: UDP 리스너 시작 (비동기)
    # ─────────────────────────────────────────────────────────────────────────
    
    if USE_THREADING:
        collector.running = True
        udp_thread = threading.Thread(
            target=collector.listen_udp,
            daemon=True,
            name="UDP-Listener"
        )
        udp_thread.start()
        logger.info(f"✅ UDP 리스너 시작: {UDP_HOST}:{UDP_PORT}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 4단계: 메인 분석 루프
    # ─────────────────────────────────────────────────────────────────────────
    
    logger.info("\n📊 분석 루프 시작 (Ctrl+C로 종료)")
    logger.info("="*70 + "\n")
    
    try:
        last_feedback_time = 0
        iteration = 0
        
        while True:
            iteration += 1
            
            # JSON 파일에서 최신 데이터 읽기 (폴링)
            data = collector.read_json()
            
            if data:
                # ─────────────────────────────────────────────────────────────
                # 실시간 피드백 생성 (주기적)
                # ─────────────────────────────────────────────────────────────
                
                current_time = time.time()
                if current_time - last_feedback_time > FEEDBACK_INTERVAL:
                    # 분석 수행
                    feedback = analyzer.get_feedback(data)
                    
                    # 세션 통계 업데이트
                    if 'RealtimeData' in data:
                        rt = data['RealtimeData']
                        session.positions.append(rt.get('Position', 0))
                    
                    # LMM에 전송
                    if feedback:
                        stats = session.get_statistics()
                        lmm.send_feedback(feedback, stats)
                    
                    last_feedback_time = current_time
                
                # ─────────────────────────────────────────────────────────────
                # 실시간 상태 표시 (콘솔)
                # ─────────────────────────────────────────────────────────────
                
                if 'StaticInfo' in data:
                    static = data['StaticInfo']
                    car = static.get('CarModel', 'Unknown')
                    track = static.get('Track', 'Unknown')
                
                if 'RealtimeData' in data:
                    rt = data['RealtimeData']
                    speed = rt.get('SpeedKmh', 0)
                    lap = rt.get('CurrentTime', '--.--')
                    fuel = rt.get('Fuel', 0)
                    pos = rt.get('Position', 0)
                    
                    # 한 줄로 상태 출력 (진행도 표시)
                    status = f"[{iteration:5d}] {car:12s} @ {track:12s} | "
                    status += f"Speed: {speed:6.1f} km/h | Lap: {lap:10s} | Fuel: {fuel:6.1f}L | Pos: {pos}"
                    print(status, end='\r')
            
            time.sleep(POLL_INTERVAL)  # CPU 사용량 절감
    
    except KeyboardInterrupt:
        logger.info("\n\n프로그램 종료 신호 수신 (Ctrl+C)")
        collector.running = False
        
        # ─────────────────────────────────────────────────────────────────────
        # 5단계: 최종 통계 출력
        # ─────────────────────────────────────────────────────────────────────
        
        session.load_csv_history(str(CSV_FILE))  # 최신 데이터 재로드
        stats = session.get_statistics()
        trend = session.get_trend()
        
        logger.info("\n" + "="*70)
        logger.info("📊 세션 최종 통계")
        logger.info("="*70)
        
        if stats:
            logger.info(f"  총 데이터 점: {len(session.lap_times)}")
            logger.info(f"  평균 랩 타임: {stats.get('avg_lap_time', 'N/A'):.0f}ms ({stats.get('avg_lap_time', 0)/1000:.2f}초)")
            logger.info(f"  베스트 랩: {stats.get('best_lap_time', 'N/A'):.0f}ms ({stats.get('best_lap_time', 0)/1000:.2f}초)")
            logger.info(f"  평균 속도: {stats.get('avg_speed', 'N/A'):.1f} km/h")
            logger.info(f"  최고 속도: {stats.get('max_speed', 'N/A'):.1f} km/h")
            logger.info(f"  최고 순위: {stats.get('best_position', 'N/A')}")
            logger.info(f"  마지막 순위: {stats.get('current_position', 'N/A')}")
        
        logger.info(f"  추세: {trend}")
        logger.info("="*70)
        logger.info(f"📁 로그 저장 위치: {LOG_FILE}")
        logger.info("프로그램 종료.\n")


if __name__ == "__main__":
    main()

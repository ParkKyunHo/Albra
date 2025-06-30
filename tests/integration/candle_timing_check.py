#!/usr/bin/env python3
"""
캔들 종가 기준 체크 검증 스크립트 (간단 버전)
"""

from datetime import datetime, timedelta
import time

def check_candle_timing():
    """현재 시간이 신호 체크 타이밍인지 확인"""
    current_time = datetime.now()
    current_minute = current_time.minute
    
    # 15분 캔들 시작 시간
    candle_start = (current_minute // 15) * 15
    candle_time = current_time.replace(minute=candle_start, second=0, microsecond=0)
    
    # 캔들 완성 후 경과 시간
    seconds_since_candle = (current_time - candle_time).total_seconds()
    
    # 다음 캔들까지 남은 시간
    next_candle = candle_time + timedelta(minutes=15)
    time_to_next = (next_candle - current_time).total_seconds()
    
    print(f"\n{'='*50}")
    print(f"현재 시간: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"현재 캔들: {candle_time.strftime('%H:%M')} ~ {next_candle.strftime('%H:%M')}")
    print(f"캔들 완성 후: {int(seconds_since_candle)}초 경과")
    print(f"다음 캔들까지: {int(time_to_next // 60)}분 {int(time_to_next % 60)}초")
    
    # 신호 체크 가능 여부
    if 30 <= seconds_since_candle <= 90:
        print(f"\n✅ 신호 체크 가능 시간대입니다!")
        print(f"   (캔들 완성 후 30~90초 사이)")
    else:
        print(f"\n⏸️  신호 체크 대기 중...")
        if seconds_since_candle < 30:
            print(f"   ({30 - int(seconds_since_candle)}초 후 체크 시작)")
        else:
            print(f"   (다음 캔들을 기다리는 중)")
    
    return seconds_since_candle

def monitor_candle_cycle():
    """15분 동안 캔들 사이클 모니터링"""
    print("\n15분 캔들 사이클 모니터링 시작...")
    print("(Ctrl+C로 중단)")
    
    check_count = 0
    last_checked_candle = None
    
    try:
        while True:
            current_time = datetime.now()
            current_minute = current_time.minute
            candle_start = (current_minute // 15) * 15
            candle_time = current_time.replace(minute=candle_start, second=0, microsecond=0)
            
            seconds_since = (current_time - candle_time).total_seconds()
            
            # 체크 타이밍인지 확인
            if 30 <= seconds_since <= 90:
                # 이번 캔들에서 첫 체크인지 확인
                if last_checked_candle != candle_time:
                    check_count += 1
                    print(f"\n[체크 #{check_count}] {current_time.strftime('%H:%M:%S')}")
                    print(f"  📊 {candle_time.strftime('%H:%M')} 캔들 체크!")
                    print(f"  ⏱️  캔들 완성 후 {int(seconds_since)}초")
                    last_checked_candle = candle_time
            
            # 상태 표시 (1줄로)
            status = "✅ 체크 중" if 30 <= seconds_since <= 90 else "⏸️  대기 중"
            print(f"\r{current_time.strftime('%H:%M:%S')} - {status} - 캔들: {candle_time.strftime('%H:%M')} (+{int(seconds_since)}s)", end='', flush=True)
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n\n모니터링 종료. 총 {check_count}회 체크 수행")

def show_next_check_times():
    """다음 체크 시간 표시"""
    current_time = datetime.now()
    
    print(f"\n다음 신호 체크 시간:")
    print(f"{'='*30}")
    
    for i in range(4):
        # 다음 15분 캔들 시간 계산
        next_candle_minutes = ((current_time.minute // 15) + i + 1) * 15
        next_candle_hour = current_time.hour + (next_candle_minutes // 60)
        next_candle_minutes = next_candle_minutes % 60
        
        # 날짜가 바뀌는 경우 처리
        next_date = current_time.date()
        if next_candle_hour >= 24:
            next_candle_hour = next_candle_hour % 24
            next_date = next_date + timedelta(days=1)
        
        candle_time = current_time.replace(
            hour=next_candle_hour,
            minute=next_candle_minutes,
            second=0,
            microsecond=0
        )
        
        # 체크 시작 시간 (캔들 완성 후 30초)
        check_start = candle_time + timedelta(seconds=30)
        check_end = candle_time + timedelta(seconds=90)
        
        print(f"{i+1}. 캔들: {candle_time.strftime('%H:%M')} → 체크: {check_start.strftime('%H:%M:%S')} ~ {check_end.strftime('%H:%M:%S')}")

def main():
    """메인 실행"""
    while True:
        print(f"\n{'='*50}")
        print("캔들 종가 기준 체크 검증 도구")
        print(f"{'='*50}")
        print("1. 현재 캔들 타이밍 체크")
        print("2. 15분 사이클 모니터링")
        print("3. 다음 체크 시간 확인")
        print("4. 종료")
        
        choice = input("\n선택하세요 (1-4): ")
        
        if choice == '1':
            check_candle_timing()
        elif choice == '2':
            monitor_candle_cycle()
        elif choice == '3':
            show_next_check_times()
        elif choice == '4':
            print("종료합니다.")
            break
        else:
            print("잘못된 선택입니다.")
        
        if choice in ['1', '3']:
            input("\n계속하려면 Enter를 누르세요...")

if __name__ == "__main__":
    main()

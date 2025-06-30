#!/usr/bin/env python3
"""
포지션 캐시 정리 스크립트
오래된 캐시로 인한 포지션 감지 문제 해결
"""

import os
import json
from datetime import datetime

def clear_position_cache():
    """포지션 캐시를 백업하고 비웁니다"""
    cache_path = "C:\\AlbraTrading\\state\\position_cache.json"
    
    if not os.path.exists(cache_path):
        print("포지션 캐시 파일이 없습니다.")
        return
    
    # 백업
    with open(cache_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    backup_path = f"C:\\AlbraTrading\\state\\position_cache_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"백업 완료: {backup_path}")
    
    # 캐시 비우기
    empty_cache = {
        "data": {},
        "metadata": {
            "saved_at": datetime.now().isoformat(),
            "version": "1.0",
            "cleared_by": "manual_clear_script"
        }
    }
    
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(empty_cache, f, indent=2, ensure_ascii=False)
    
    print("포지션 캐시가 비워졌습니다.")
    print("다음 sync에서 모든 포지션이 새 포지션으로 감지됩니다.")

if __name__ == "__main__":
    clear_position_cache()

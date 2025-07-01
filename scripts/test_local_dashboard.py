#!/usr/bin/env python3
"""
로컬 테스트용 대시보드 실행 스크립트
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.web.dashboard import DashboardApp
from src.web.performance_dashboard import PerformanceDashboard
from src.analysis.performance_tracker import PerformanceTracker
import logging

logging.basicConfig(level=logging.INFO)

def run_test_dashboard():
    """테스트용 대시보드 실행"""
    
    # DashboardApp 생성
    app = DashboardApp()
    
    # PerformanceTracker 생성 (빈 데이터)
    performance_tracker = PerformanceTracker(data_dir="data/performance_test")
    
    # 성과 대시보드 설정
    app.performance_tracker = performance_tracker
    app.setup_performance_dashboard()
    
    print("=" * 60)
    print("로컬 테스트 대시보드 시작")
    print("=" * 60)
    print("http://localhost:5000 - 메인 대시보드")
    print("http://localhost:5000/performance - 성과 분석 대시보드")
    print("http://localhost:5000/api/routes - API 라우트 목록")
    print("=" * 60)
    print("종료하려면 Ctrl+C를 누르세요")
    
    # Flask 앱 실행
    app.app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == "__main__":
    run_test_dashboard()
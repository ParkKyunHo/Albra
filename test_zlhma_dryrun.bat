@echo off
REM ZLHMA EMA Cross 전략 드라이런 테스트
REM 작성일: 2025-01-02

echo ========================================
echo ZLHMA EMA Cross 전략 드라이런 테스트
echo ========================================
echo.

REM Python 경로 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되지 않았거나 PATH에 없습니다.
    pause
    exit /b 1
)

echo [1] 통합 테스트 실행 중...
python scripts\test_zlhma_integration.py
if errorlevel 1 (
    echo [오류] 통합 테스트 실패
    pause
    exit /b 1
)

echo.
echo [2] 드라이런 모드 실행 준비
echo.
echo 다음 명령을 실행하여 드라이런 테스트를 시작하세요:
echo python src\main.py --strategies ZLHMA_EMA_CROSS --dry-run
echo.
echo 또는 이 배치 파일을 계속 진행하려면 아무 키나 누르세요...
pause >nul

echo.
echo [3] 드라이런 모드 시작 (Ctrl+C로 중단)
echo.
python src\main.py --strategies ZLHMA_EMA_CROSS --dry-run

pause

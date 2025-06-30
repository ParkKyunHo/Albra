@echo off
echo ====================================
echo   배포 전 안전 체크리스트
echo ====================================
echo.

set /p CHECK1="1. 현재 활성 포지션을 확인했나요? (y/n): "
if /i not "%CHECK1%"=="y" goto :ABORT

set /p CHECK2="2. 포지션의 손익 상태를 확인했나요? (y/n): "
if /i not "%CHECK2%"=="y" goto :ABORT

set /p CHECK3="3. 중요한 가격 레벨 근처인지 확인했나요? (y/n): "
if /i not "%CHECK3%"=="y" goto :ABORT

set /p CHECK4="4. 배포 중 20-30초 모니터링 공백을 감수할 수 있나요? (y/n): "
if /i not "%CHECK4%"=="y" goto :ABORT

echo.
echo ✅ 모든 체크 완료!
echo.
echo 포지션 정보:
echo -------------
set /p POSITIONS="활성 포지션 수: "
set /p PNL="현재 총 손익(%): "
echo.

set /p CONFIRM="정말 배포를 진행하시겠습니까? (yes/no): "
if /i not "%CONFIRM%"=="yes" goto :ABORT

echo.
echo 배포를 진행합니다...
call deploy.bat
goto :END

:ABORT
echo.
echo ❌ 배포가 취소되었습니다.
echo.
echo 권장사항:
echo - 포지션이 없을 때 배포
echo - 또는 손절/익절 레벨에서 멀 때 배포
echo - 또는 수동으로 모니터링 가능할 때 배포
echo.

:END
pause

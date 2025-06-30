@echo off
echo ====================================
echo   AlbraTrading Deployment Script
echo      (Systemd Version)
echo ====================================

set EC2_IP=3.39.88.164
set SSH_KEY=%USERPROFILE%\.ssh\trading-bot-key
set LOCAL_DIR=C:\AlbraTrading
set REMOTE_DIR=/home/ubuntu/AlbraTrading

color 0A

echo DEBUG: EC2_IP=%EC2_IP%
echo DEBUG: SSH_KEY=%SSH_KEY%
echo DEBUG: LOCAL_DIR=%LOCAL_DIR%
echo DEBUG: REMOTE_DIR=%REMOTE_DIR%
echo.
echo.
echo [1/10] Running local verification...
cd /d "%LOCAL_DIR%"
if exist "scripts\verify_code.py" (
    python "scripts\verify_code.py"
    if errorlevel 1 (
        echo ERROR: Code verification failed!
        pause
        exit /b 1
    )
) else (
    echo WARNING: verify_code.py not found, skipping verification...
)

echo [2/10] Checking local files...
if not exist "src\main.py" (
    echo ERROR: main.py not found in %LOCAL_DIR%\src\
    pause
    exit /b 1
)

echo [3/10] Stopping existing services...
echo   - Checking current service status...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "%REMOTE_DIR%/scripts/setup_systemd_multi.sh status 2>/dev/null || echo 'No active service'"
echo   - Stopping all services...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl stop albratrading 2>/dev/null || true"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl stop albratrading-single 2>/dev/null || true"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl stop albratrading-multi 2>/dev/null || true"

echo [4/10] Creating remote directory structure...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "mkdir -p %REMOTE_DIR%/{src/{core,strategies,utils,web/templates,monitoring,analysis,core/multi_account},config,state,data,logs,scripts/systemd}"

echo [5/10] Uploading project files...
echo   - Uploading source code...
scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\src\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/src/

echo   - Ensuring all core modules are uploaded...
scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\src\core\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/src/core/
scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\src\strategies\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/src/strategies/
scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\src\utils\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/src/utils/
scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\src\web\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/src/web/

echo   - Uploading monitoring modules...
if exist "%LOCAL_DIR%\src\monitoring" (
    scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\src\monitoring\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/src/monitoring/
)

echo   - Uploading analysis modules...
if exist "%LOCAL_DIR%\src\analysis" (
    scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\src\analysis\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/src/analysis/
)

echo   - Uploading multi-account modules...
if exist "%LOCAL_DIR%\src\core\multi_account" (
    scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\src\core\multi_account\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/src/core/multi_account/
)

echo   - Uploading config files...
scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\config\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/config/

echo   - Uploading scripts...
if exist "%LOCAL_DIR%\scripts\*" (
    scp -i "%SSH_KEY%" -r "%LOCAL_DIR%\scripts\*" ubuntu@%EC2_IP%:%REMOTE_DIR%/scripts/
    echo   - Setting script permissions...
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "chmod +x %REMOTE_DIR%/scripts/*.sh %REMOTE_DIR%/scripts/*.py 2>/dev/null || true"
    
    echo   - Uploading systemd service files...
    scp -i "%SSH_KEY%" "%LOCAL_DIR%\scripts\systemd\albratrading-single.service" ubuntu@%EC2_IP%:%REMOTE_DIR%/scripts/systemd/
    scp -i "%SSH_KEY%" "%LOCAL_DIR%\scripts\systemd\albratrading-multi.service" ubuntu@%EC2_IP%:%REMOTE_DIR%/scripts/systemd/
)

echo   - Uploading requirements.txt...
scp -i "%SSH_KEY%" "%LOCAL_DIR%\requirements.txt" ubuntu@%EC2_IP%:%REMOTE_DIR%/

echo   - Uploading .env file...
if exist "%LOCAL_DIR%\.env" (
    scp -i "%SSH_KEY%" "%LOCAL_DIR%\.env" ubuntu@%EC2_IP%:%REMOTE_DIR%/
) else (
    echo WARNING: .env file not found! Bot may not start properly.
)

echo [6/10] Setting up Python virtual environment...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd %REMOTE_DIR% && python3 -m venv venv || true"

echo [7/10] Installing/Updating dependencies...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd %REMOTE_DIR% && source venv/bin/activate && pip install --upgrade pip"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd %REMOTE_DIR% && source venv/bin/activate && pip install -r requirements.txt --upgrade"
echo   - Verifying critical dependencies...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd %REMOTE_DIR% && source venv/bin/activate && pip install aiofiles aiohttp aiosqlite --upgrade"

echo [8/10] Setting permissions...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "chmod +x %REMOTE_DIR%/src/main.py 2>/dev/null || true"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "chmod -R 755 %REMOTE_DIR%/src/"
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "chown -R ubuntu:ubuntu %REMOTE_DIR%/"

echo [9/10] Creating deployment timestamp...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "echo 'Deployed at: %DATE% %TIME%' > %REMOTE_DIR%/deployment_timestamp.txt"

echo [10/10] Setting up and starting service...
echo.
echo Select deployment mode:
echo   1. Single Account Mode (Default)
echo   2. Multi Account Mode
echo.
set /p MODE_CHOICE=Enter choice (1 or 2) [Default: 1]: 
if "%MODE_CHOICE%"=="" set MODE_CHOICE=1

echo.
echo   - Ensuring setup script is executable...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "chmod +x %REMOTE_DIR%/scripts/setup_systemd_multi.sh"

echo   - Checking if setup script exists...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "ls -la %REMOTE_DIR%/scripts/setup_systemd_multi.sh"

if "%MODE_CHOICE%"=="2" (
    echo   - Setting up multi-account mode...
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd %REMOTE_DIR% && bash ./scripts/setup_systemd_multi.sh multi"
    set SERVICE_NAME=albratrading-multi
) else (
    echo   - Setting up single-account mode...
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd %REMOTE_DIR% && bash ./scripts/setup_systemd_multi.sh single"
    set SERVICE_NAME=albratrading-single
)

REM Windows batch variable workaround
if "%MODE_CHOICE%"=="2" (
    set "SERVICE_CHECK=albratrading-multi"
) else (
    set "SERVICE_CHECK=albratrading-single"
)

echo.
echo Waiting 15 seconds for startup...
timeout /t 15 /nobreak > nul

echo.
echo Starting service...
if "%MODE_CHOICE%"=="2" (
    echo   - Starting albratrading-multi service...
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl start albratrading-multi"
    timeout /t 5 /nobreak > nul
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl is-active albratrading-multi"
) else (
    echo   - Starting albratrading-single service...
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl start albratrading-single"
    timeout /t 5 /nobreak > nul
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl is-active albratrading-single"
)
set SERVICE_STATUS=%ERRORLEVEL%

if %SERVICE_STATUS% NEQ 0 (
    echo.
    echo   - Service failed to start. Checking for Python errors...
    echo.
    echo   [Testing Python directly]:
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd %REMOTE_DIR% && source venv/bin/activate && python src/main.py --validate"
    echo.
    echo   [Checking service logs]:
    if "%MODE_CHOICE%"=="2" (
        ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo journalctl -u albratrading-multi -n 100 --no-pager"
    ) else (
        ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo journalctl -u albratrading-single -n 100 --no-pager"
    )
    echo.
    echo   [Checking Python dependencies]:
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd %REMOTE_DIR% && source venv/bin/activate && pip list | grep -E 'binance|aiohttp|pandas'"
) else (
    echo   - Service started successfully!
)

echo.
echo ====================================
echo         DEPLOYMENT STATUS
echo ====================================

echo.
echo [Service Status]
if "%MODE_CHOICE%"=="2" (
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl status albratrading-multi --no-pager | head -20"
) else (
    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl status albratrading-single --no-pager | head -20"
)

echo.
echo [Running deployment check...]
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd %REMOTE_DIR% && chmod +x scripts/check_deployment_multi.sh 2>/dev/null && ./scripts/check_deployment_multi.sh"

echo.
echo ====================================
echo Deployment completed!
echo.
echo Quick commands:
if "%MODE_CHOICE%"=="2" (
    echo   Status:  ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl status albratrading-multi"
    echo   Logs:    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo journalctl -u albratrading-multi -f"
    echo   CLI:     ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && python scripts/multi_account_cli.py status"
) else (
    echo   Status:  ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl status albratrading-single"
    echo   Logs:    ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo journalctl -u albratrading-single -f"
)
echo   Check:   ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && ./scripts/check_deployment_multi.sh"
echo   Direct:  ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python src/main.py"
echo ====================================

pause
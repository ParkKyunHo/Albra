@echo off
echo ====================================
echo   Fixing Dependencies
echo ====================================

set EC2_IP=43.201.76.89
set SSH_KEY=%USERPROFILE%\.ssh\trading-bot4

echo.
echo [1] Stopping service...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl stop albratrading"

echo.
echo [2] Updating pip...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && pip install --upgrade pip"

echo.
echo [3] Installing aiofiles specifically...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && pip install aiofiles==23.2.1"

echo.
echo [4] Reinstalling all dependencies...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && pip install -r requirements.txt --upgrade"

echo.
echo [5] Verifying aiofiles installation...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python -c 'import aiofiles; print(\"aiofiles version:\", aiofiles.__version__)'"

echo.
echo [6] Testing imports...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "cd /home/ubuntu/AlbraTrading && source venv/bin/activate && python -c 'from src.core.event_logger import get_event_logger; print(\"Event logger import: OK\")'"

echo.
echo [7] Starting service...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl start albratrading"

echo.
echo [8] Waiting for service to start...
timeout /t 10 /nobreak

echo.
echo [9] Checking service status...
ssh -i "%SSH_KEY%" ubuntu@%EC2_IP% "sudo systemctl status albratrading --no-pager | head -20"

pause

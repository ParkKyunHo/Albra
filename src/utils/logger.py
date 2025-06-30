# src/utils/logger.py
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import colorlog

def setup_logger(name: str = None, log_level: str = 'INFO', 
                log_dir: str = 'logs', console: bool = True, 
                file: bool = True) -> logging.Logger:
    """로거 설정"""
    
    # 로그 디렉토리 생성
    if file:
        os.makedirs(log_dir, exist_ok=True)
    
    # 로거 생성
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 기존 핸들러 제거
    logger.handlers.clear()
    
    # 포맷터 설정
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 콘솔 핸들러 (컬러)
    if console:
        console_formatter = colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s%(reset)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)
    
    # 파일 핸들러
    if file:
        # 일별 로그 파일
        daily_handler = TimedRotatingFileHandler(
            filename=os.path.join(log_dir, f'{name or "trading"}.log'),
            when='midnight',
            interval=1,
            backupCount=30,  # 30일 보관
            encoding='utf-8'
        )
        daily_handler.setFormatter(file_formatter)
        daily_handler.setLevel(logging.INFO)
        logger.addHandler(daily_handler)
        
        # 에러 전용 로그
        error_handler = RotatingFileHandler(
            filename=os.path.join(log_dir, f'{name or "trading"}_error.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setFormatter(file_formatter)
        error_handler.setLevel(logging.ERROR)
        logger.addHandler(error_handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """로거 가져오기"""
    return logging.getLogger(name)

# 기본 로거 설정
def setup_default_logging(log_level: str = 'INFO'):
    """기본 로깅 설정"""
    # 루트 로거 설정
    setup_logger(None, log_level)
    
    # 특정 모듈 로그 레벨 조정
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('binance').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    # 중요 모듈은 상세 로깅
    logging.getLogger('src.core').setLevel(logging.DEBUG)
    logging.getLogger('src.strategies').setLevel(logging.DEBUG)

# 기본 로거 생성 및 export
logger = setup_logger('AlbraTrading')
setup_default_logging()

# 로거 사용 예시를 위한 __all__ 정의
__all__ = ['logger', 'setup_logger', 'get_logger', 'setup_default_logging']
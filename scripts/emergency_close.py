# 긴급 손절 스크립트
import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, '.')
from src.core.binance_api import BinanceAPI

load_dotenv()

async def emergency_close_all():
    """모든 포지션 긴급 청산"""
    api = BinanceAPI(
        api_key=os.getenv('BINANCE_API_KEY'),
        secret_key=os.getenv('BINANCE_SECRET_KEY'),
        testnet=False
    )
    await api.initialize()
    
    positions = await api.get_positions()
    active = [p for p in positions if float(p['positionAmt']) != 0]
    
    if not active:
        print("청산할 포지션이 없습니다.")
        return
    
    print(f"\n⚠️  {len(active)}개 포지션을 청산합니다:")
    for pos in active:
        print(f"  - {pos['symbol']}: {pos['positionAmt']}")
    
    confirm = input("\n정말 청산하시겠습니까? (yes): ")
    if confirm != 'yes':
        print("취소되었습니다.")
        return
    
    for pos in active:
        try:
            symbol = pos['symbol']
            amount = float(pos['positionAmt'])
            
            # 반대 주문으로 청산
            if amount > 0:
                await api.create_market_order(symbol, 'SELL', abs(amount))
            else:
                await api.create_market_order(symbol, 'BUY', abs(amount))
            
            print(f"✅ {symbol} 청산 완료")
        except Exception as e:
            print(f"❌ {symbol} 청산 실패: {e}")

if __name__ == "__main__":
    asyncio.run(emergency_close_all())

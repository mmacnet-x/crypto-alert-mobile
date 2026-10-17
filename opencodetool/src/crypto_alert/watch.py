"""2단계 검증 CLI: 시세 스냅샷 + 캔들 + 실시간 스트림 출력.

실행: ``python -m crypto_alert.watch``
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import aiohttp

from crypto_alert.config import load_watchlist
from crypto_alert.exchanges.base import ExchangeClient, ExchangeError, Interval, Ticker
from crypto_alert.exchanges.binance import BinanceClient
from crypto_alert.exchanges.okx import OKXClient
from crypto_alert.exchanges.upbit import UpbitClient

logger = logging.getLogger(__name__)


def format_price(price: float) -> str:
    """가격을 읽기 좋은 형태로 포맷한다."""
    if price >= 100:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:,.4f}"
    if price == 0:
        return "0"
    return f"{price:.10f}".rstrip("0")


def format_ticker(prefix: str, ticker: Ticker) -> str:
    percent = ticker.change_rate * 100
    clock = ticker.time.astimezone().strftime("%H:%M:%S")
    return (
        f"[{prefix}] {clock}  {ticker.symbol:<12}  {format_price(ticker.price):>16}"
        f"  {percent:>+7.2f}%  vol {ticker.volume:,.2f}"
    )


async def run(duration: float) -> None:
    """스냅샷 → 캔들 샘플 → 실시간 스트림 순으로 확인한다."""
    watchlist = load_watchlist()
    async with aiohttp.ClientSession() as session:
        clients: dict[str, tuple[ExchangeClient, str]] = {
            "upbit": (UpbitClient(session), "업비트"),
            "binance": (BinanceClient(session), "바이낸스"),
            "okx": (OKXClient(session), "OKX"),
        }

        # 1) 현재가 스냅샷
        print("=== 현재가 스냅샷 ===")
        for exchange, (client, label) in clients.items():
            symbols = watchlist.get(exchange, [])
            if not symbols:
                print(f"[{label}] 감시 종목 없음")
                continue
            try:
                tickers = await client.fetch_tickers(symbols)
            except ExchangeError as exc:
                print(f"[{label}] 조회 실패: {exc}")
                continue
            print(f"[{label}] {len(tickers)}/{len(symbols)}종목")
            for ticker in tickers:
                print(format_ticker(label, ticker))

        # 2) 캔들 샘플 (대표 종목 15분봉 3개)
        print("\n=== 캔들 샘플 (15분봉 3개) ===")
        samples = [
            ("BTC/KRW", "upbit", "업비트"),
            ("BTC/USDT", "binance", "바이낸스"),
            ("PI/USDT", "okx", "OKX"),
        ]
        for symbol, exchange, label in samples:
            client = clients[exchange][0]
            try:
                candles = await client.fetch_candles(symbol, Interval.M15, limit=3)
            except ExchangeError as exc:
                print(f"[{label}] {symbol} 캔들 실패: {exc}")
                continue
            for candle in candles:
                clock = candle.time.astimezone().strftime("%H:%M")
                print(
                    f"[{label}] {clock}  {candle.symbol:<12}"
                    f"  O {format_price(candle.open)}  H {format_price(candle.high)}"
                    f"  L {format_price(candle.low)}  C {format_price(candle.close)}"
                    f"  V {candle.volume:,.2f}"
                )

        # 3) 실시간 스트림
        print("\n=== 실시간 시세 (Ctrl+C로 종료) ===")
        stop = asyncio.Event()
        symbol_labels = {
            symbol: label
            for exchange, (_client, label) in clients.items()
            for symbol in watchlist.get(exchange, [])
        }

        def on_ticker(ticker: Ticker) -> None:
            label = symbol_labels.get(ticker.symbol)
            if label is None:
                label = "업비트" if ticker.symbol.endswith("/KRW") else "바이낸스"
            print(format_ticker(label, ticker), flush=True)

        tasks = [
            asyncio.create_task(client.stream_tickers(watchlist.get(key, []), on_ticker, stop))
            for key, (client, _label) in clients.items()
            if watchlist.get(key)
        ]
        if not tasks:
            print("감시 종목이 없어 스트림을 시작하지 않습니다.")
            return
        try:
            if duration > 0:
                await asyncio.sleep(duration)
            else:
                await stop.wait()
        finally:
            stop.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        print("종료되었습니다.")


def main() -> int:
    parser = argparse.ArgumentParser(description="2단계 시세 수신 검증 CLI")
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="실시간 스트림 확인 시간(초), 0이면 Ctrl+C까지 실행",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(run(args.duration))
    return 0


if __name__ == "__main__":  # pragma: no cover — 직접 실행 전용
    raise SystemExit(main())

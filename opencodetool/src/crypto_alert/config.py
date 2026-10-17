"""감시 코인 목록 설정 (JSON 파일로 관리 → 언제든 추가/삭제 가능).

파일 위치: ``src/crypto_alert/watchlist.json`` (패키징 후에는 exe 옆)
수정 방법: 파일을 직접 편집하거나 :func:`add_symbol` / :func:`remove_symbol` 사용.
나중에 5단계 UI에서 버튼으로 연결된다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from crypto_alert.exchanges.symbols import SymbolError, normalize_symbol
from crypto_alert.paths import app_data_dir

__all__ = [
    "EXCHANGES",
    "WatchlistError",
    "add_symbol",
    "load_watchlist",
    "remove_symbol",
    "watchlist_path",
    "write_watchlist",
]

EXCHANGES: Final[tuple[str, ...]] = ("upbit", "binance", "okx")

_DEFAULT_DATA: Final[dict[str, list[str]]] = {
    "binance": [
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "XRP/USDT",
        "XLM/USDT",
        "WLD/USDT",
        "BTTC/USDT",
    ],
    "okx": [
        "PI/USDT",
    ],
    "upbit": [
        "BTC",
        "ETH",
        "XRP",
        "XLM",
        "ADA",
        "WLD",
        "SOL",
        "SUI",
        "SHIB",
        "BTT",
        "MED",
        "BLUR",
        "AVAX",
        "TRX",
        "LINK",
        "APT",
        "HBAR",
        "JTO",
        "BCH",
        "FIL",
        "SEI",
        "POL",
        "DOT",
        "ENS",
        "XEC",
        "ICX",
    ],
}


class WatchlistError(ValueError):
    """감시 목록 설정이 잘못되었을 때 발생."""


def watchlist_path() -> Path:
    """감시 목록 JSON 파일 경로를 반환한다."""
    return app_data_dir() / "watchlist.json"


def _normalize(exchange: str, raw: str) -> str:
    try:
        return normalize_symbol(exchange, raw)
    except SymbolError as exc:
        raise WatchlistError(str(exc)) from exc


def load_watchlist(path: Path | None = None) -> dict[str, list[str]]:
    """감시 목록을 읽어 정규화된 {거래소: [표준심볼]}로 반환한다.

    파일이 없으면 기본 목록으로 생성한다.
    """
    target = path or watchlist_path()
    if not target.exists():
        write_watchlist(_DEFAULT_DATA, target)
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise WatchlistError(f"감시 목록 형식이 잘못되었습니다: {target}")
    unknown = set(raw) - set(EXCHANGES)
    if unknown:
        raise WatchlistError(f"알 수 없는 거래소 키: {sorted(unknown)}")

    result: dict[str, list[str]] = {}
    for exchange in EXCHANGES:
        items = raw.get(exchange, [])
        if not isinstance(items, list):
            raise WatchlistError(f"[{exchange}] 목록은 배열이어야 합니다")
        seen: set[str] = set()
        symbols: list[str] = []
        for item in items:
            if not isinstance(item, str) or not item.strip():
                raise WatchlistError(f"[{exchange}] 잘못된 항목: {item!r}")
            symbol = _normalize(exchange, item)
            if symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
        result[exchange] = symbols
    return result


def write_watchlist(data: Mapping[str, Sequence[str]], path: Path | None = None) -> None:
    """감시 목록을 파일에 저장한다 (파일 표기: 업비트는 티커, 바이낸스/OKX는 PAIR)."""
    target = path or watchlist_path()
    payload: dict[str, list[str]] = {}
    for exchange in EXCHANGES:
        symbols = data.get(exchange, [])
        if exchange == "upbit":
            payload[exchange] = [_base_of(item) for item in symbols]
        else:
            payload[exchange] = [str(item) for item in symbols]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def add_symbol(exchange: str, raw_symbol: str, path: Path | None = None) -> bool:
    """감시 목록에 종목을 추가한다. 이미 있으면 False를 반환한다."""
    if exchange not in EXCHANGES:
        raise WatchlistError(f"알 수 없는 거래소: {exchange!r}")
    watchlist = load_watchlist(path)
    symbol = _normalize(exchange, raw_symbol)
    if symbol in watchlist[exchange]:
        return False
    watchlist[exchange].append(symbol)
    write_watchlist(watchlist, path)
    return True


def remove_symbol(exchange: str, raw_symbol: str, path: Path | None = None) -> bool:
    """감시 목록에서 종목을 제거한다. 없으면 False를 반환한다."""
    if exchange not in EXCHANGES:
        raise WatchlistError(f"알 수 없는 거래소: {exchange!r}")
    watchlist = load_watchlist(path)
    symbol = _normalize(exchange, raw_symbol)
    if symbol not in watchlist[exchange]:
        return False
    watchlist[exchange].remove(symbol)
    write_watchlist(watchlist, path)
    return True


def _base_of(symbol: str) -> str:
    """``BTC/KRW`` → ``BTC`` (업비트 파일 표기)."""
    return symbol.split("/")[0]

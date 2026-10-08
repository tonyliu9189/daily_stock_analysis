# -*- coding: utf-8 -*-
"""台灣集中市場與上櫃市場的官方每日成交資訊。"""

import logging
import math
from datetime import date
from typing import Any, Dict, List

import requests

from src.core.trading_calendar import get_effective_trading_date

logger = logging.getLogger(__name__)


def _number(value: Any) -> float:
    number = float(str(value).replace(',', '').strip())
    if not math.isfinite(number):
        raise ValueError('台股行情包含非有限數值')
    return number


def _trade_date(value: Any) -> date:
    text = str(value).replace('/', '').replace('-', '').strip()
    if len(text) == 7:  # 民國年月日，例如 1151007。
        text = str(int(text[:3]) + 1911) + text[3:]
    if len(text) != 8:
        raise ValueError('台股行情日期長度無效')
    return date.fromisoformat(f'{text[:4]}-{text[4:6]}-{text[6:8]}')


def get_tw_market_indices() -> List[Dict[str, Any]]:
    """使用實際資料日期，不混入中國行情或把不同交易日合併成同一天。"""
    target_date = get_effective_trading_date('tw')
    sources = (
        ('TWII', '台灣加權指數', 'TWSE',
         'https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK', 'TAIEX', 'TradeValue'),
        ('TWOII', '櫃買指數', 'TPEx',
         'https://www.tpex.org.tw/openapi/v1/tpex_daily_trading_index', 'TPExIndex', 'TradeAmount'),
    )
    indices = []
    for code, name, source, url, close_key, amount_key in sources:
        try:
            response = requests.get(url, timeout=(5, 15))
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError('台股行情格式不是清單')
            dated_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    trade_date = _trade_date(row['Date'])
                except (KeyError, TypeError, ValueError):
                    continue
                if trade_date <= target_date:
                    dated_rows.append((trade_date, row))
            if not dated_rows:
                raise ValueError('沒有符合交易日期的台股行情')
            trade_date, row = max(dated_rows, key=lambda item: item[0])
            close = _number(row[close_key])
            change = _number(row['Change'])
            prev_close = close - change
            volume = _number(row['TradeVolume'])
            amount = _number(row[amount_key])
            if close <= 0 or prev_close <= 0 or volume < 0 or amount < 0:
                raise ValueError('台股行情數值無效')
            indices.append({
                'code': code, 'name': name, 'current': close, 'change': change,
                'change_pct': change / prev_close * 100, 'prev_close': prev_close,
                'open': 0.0, 'high': 0.0, 'low': 0.0, 'amplitude': 0.0,
                'volume': volume, 'amount': amount, 'trade_date': trade_date.isoformat(),
                'source': source, 'source_url': url,
            })
        except (requests.RequestException, TypeError, ValueError, KeyError) as exc:
            logger.warning('[台股總覽] %s 每日行情取得失敗：%s', source, exc)
    if not indices:
        return []
    latest_date = max(item['trade_date'] for item in indices)
    # 延遲發布的來源不與較新的來源混算；報告會標示缺少的市場。
    current = [item for item in indices if item['trade_date'] == latest_date]
    if len(current) < len(sources):
        logger.warning('[台股總覽] %s 僅有 %d 個市場的同日資料', latest_date, len(current))
    return current

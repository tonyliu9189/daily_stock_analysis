# -*- coding: utf-8 -*-
"""台灣集中市場與上櫃市場的官方每日成交資訊。"""

import logging
import math
from datetime import date
from typing import Any, Dict, List

import requests
import exchange_calendars as xcals

from src.core.trading_calendar import get_effective_trading_date

logger = logging.getLogger(__name__)

_TWSE_HISTORY = 'https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK'


def _twse_history(target_date):
    """官方月資料備援；以欄位名稱解析並要求指定交易日存在。"""
    params = {'response': 'json', 'date': target_date.strftime('%Y%m%d')}
    response = requests.get(_TWSE_HISTORY, params=params, timeout=(5, 15), allow_redirects=False)
    response.raise_for_status()
    if 300 <= response.status_code < 400:
        raise ValueError('官方歷史行情重新導向')
    payload = response.json()
    fields = ['日期', '成交股數', '成交金額', '發行量加權股價指數', '漲跌點數']
    if not isinstance(payload, dict) or payload.get('stat') != 'OK':
        raise ValueError('官方歷史行情無資料')
    if _trade_date(payload.get('date')) != target_date or payload.get('hints') != '單位：元、股':
        raise ValueError('官方歷史行情回應日期或單位不符')
    columns, rows = payload.get('fields'), payload.get('data')
    if not isinstance(columns, list) or len(set(columns)) != len(columns) or not all(key in columns for key in fields) or not isinstance(rows, list):
        raise ValueError('官方歷史行情欄位無效')
    result = []
    for values in rows:
        if not isinstance(values, list) or len(values) != len(columns):
            raise ValueError('官方歷史行情欄位數量不符')
        row = dict(zip(columns, values))
        day = _trade_date(row['日期'])
        if day <= target_date:
            result.append((day, {'TradeVolume': row['成交股數'], 'TradeValue': row['成交金額'],
                                 'TAIEX': row['發行量加權股價指數'], 'Change': row['漲跌點數']}))
    if sum(day == target_date for day, _ in result) != 1:
        raise ValueError('官方歷史行情沒有唯一的指定交易日')
    return result, requests.Request('GET', _TWSE_HISTORY, params=params).prepare().url


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


def _volume_comparison(dated_rows, trade_date, volume, amount, amount_key):
    """比較實際前一交易日及前五個交易日，不以缺漏資料冒充完整樣本。"""
    result = {'previous_session': None, 'previous_5_sessions': None}
    try:
        sessions = xcals.get_calendar('XTAI').sessions_window(trade_date.isoformat(), -6)
        previous_dates = [session.date() for session in sessions if session.date() < trade_date]
        history = {}
        for row_date, row in dated_rows:
            if row_date in previous_dates:
                try:
                    values = (_number(row['TradeVolume']), _number(row[amount_key]))
                    if all(value > 0 for value in values):
                        history[row_date] = values
                except (KeyError, ValueError, TypeError):
                    continue
        if previous_dates and previous_dates[-1] in history:
            prior_volume, prior_amount = history[previous_dates[-1]]
            result['previous_session'] = {
                'trade_date': previous_dates[-1].isoformat(),
                'volume': prior_volume, 'amount': prior_amount,
                'volume_change_pct': (volume / prior_volume - 1) * 100,
                'amount_change_pct': (amount / prior_amount - 1) * 100,
            }
        if len(previous_dates) == 5 and all(day in history for day in previous_dates):
            mean_volume = sum(history[day][0] for day in previous_dates) / 5
            mean_amount = sum(history[day][1] for day in previous_dates) / 5
            result['previous_5_sessions'] = {
                'trade_dates': [day.isoformat() for day in previous_dates],
                'volume_mean': mean_volume, 'amount_mean': mean_amount,
                'volume_change_pct': (volume / mean_volume - 1) * 100,
                'amount_change_pct': (amount / mean_amount - 1) * 100,
            }
    except Exception as exc:
        logger.warning('[台股總覽] 量值比較無法完成：%s', exc)
    return result


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
                'volume_unit': 'shares', 'amount_currency': 'TWD',
                'volume_comparison': _volume_comparison(dated_rows, trade_date, volume, amount, amount_key),
            })
        except (requests.RequestException, TypeError, ValueError, KeyError) as exc:
            logger.warning('[台股總覽] %s 每日行情取得失敗：%s', source, exc)
    if not indices:
        logger.warning('[台股總覽] 主來源沒有可用指數，嘗試 TWSE 日期查詢')
    twse = next((item for item in indices if item['code'] == 'TWII'), None)
    if twse is None or twse['trade_date'] != target_date.isoformat():
        try:
            rows, url = _twse_history(target_date)
            _, row = next(item for item in rows if item[0] == target_date)
            close, change = _number(row['TAIEX']), _number(row['Change'])
            volume, amount = _number(row['TradeVolume']), _number(row['TradeValue'])
            if close <= 0 or close - change <= 0 or volume < 0 or amount < 0:
                raise ValueError('官方歷史行情數值無效')
            fresh = {'code': 'TWII', 'name': '台灣加權指數', 'current': close,
                     'change': change, 'change_pct': change / (close - change) * 100,
                     'prev_close': close - change, 'open': 0.0, 'high': 0.0, 'low': 0.0,
                     'amplitude': 0.0, 'volume': volume, 'amount': amount,
                     'trade_date': target_date.isoformat(), 'source': 'TWSE', 'source_url': url,
                     'volume_unit': 'shares', 'amount_currency': 'TWD',
                     'volume_comparison': _volume_comparison(rows, target_date, volume, amount, 'TradeValue')}
            indices = [item for item in indices if item['code'] != 'TWII']
            indices.insert(0, fresh)
            logger.info('[台股總覽] TWSE 日期查詢備援成功：%s', target_date)
        except (requests.RequestException, TypeError, ValueError, KeyError) as exc:
            logger.warning('[台股總覽] TWSE 日期查詢備援失敗：%s', exc)
    if not indices:
        return []
    latest_date = max(item['trade_date'] for item in indices)
    # 延遲發布的來源不與較新的來源混算；報告會標示缺少的市場。
    current = [item for item in indices if item['trade_date'] == latest_date]
    if len(current) < len(sources):
        logger.warning('[台股總覽] %s 僅有 %d 個市場的同日資料', latest_date, len(current))
    return current

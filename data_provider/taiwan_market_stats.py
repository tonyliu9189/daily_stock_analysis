# -*- coding: utf-8 -*-
"""台股官方每日大盤補充資料，僅接受指定交易日，不退回其他日期。

回傳 ``{trade_date, markets: {twse, tpex}}``；各市場包含 institutions、
breadth、sectors，無法確認的項目為 None，原因列於 missing_reasons。
成功項目一律附 trade_date、unit、source_url。法人金額為新臺幣元，
前三列為外資（不含自營商）、投信、自營商，最後一列為官方合計。

2026-10-08 實際核對官方 Swagger 與 JSON：
https://openapi.twse.com.tw/swagger.json
https://www.tpex.org.tw/openapi/swagger.json
TWSE BFI82U 的歷史日參數為 dayDate（date 會被忽略）；MI_INDEX 使用 date。
TPEx OpenAPI 僅提供最新日，必須核對每列 Date；不以最新日替代指定日。
TPEx 每日類股價格指數使用官網 indexSummary JSON（未列在 Swagger）。
只採官網 indexInfo/sectinx 核對的產業分類，排除大盤、主題及報酬指數。
每次呼叫最多六個 GET，無重試、無逐檔請求；各項失敗獨立降級。
"""

import logging
import math
import re
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

_TWSE_INSTITUTIONS = 'https://www.twse.com.tw/rwd/zh/fund/BFI82U'
_TWSE_MARKET = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'
_TPEX_INSTITUTIONS = 'https://www.tpex.org.tw/openapi/v1/tpex_3insti_summary'
# mainborad is the official spelling, not a local typo.
_TPEX_BREADTH = 'https://www.tpex.org.tw/openapi/v1/tpex_mainborad_highlight'
_TPEX_SECTORS = 'https://www.tpex.org.tw/www/zh-tw/afterTrading/indexSummary'
# 官方 /www/zh-tw/indexInfo/sectinx 產業分類，實際核對 2026-10-08。
_TPEX_SECTOR_NAMES = frozenset((
    '紡織纖維', '電機機械', '鋼鐵工業', '電子工業', '建材營造', '航運業', '觀光餐旅', '其他',
    '化學工業', '生技醫療', '半導體業', '電腦及週邊設備業', '光電業', '通信網路業',
    '電子零組件業', '電子通路業', '資訊服務業', '其他電子業', '文化創意業', '綠能環保', '數位雲端', '居家生活',
))
_NUMBER = re.compile(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?')


def _date(value: Any) -> str:
    text = str(value).strip().replace('/', '').replace('-', '')
    if not text.isascii() or not text.isdigit() or len(text) not in (7, 8):
        raise ValueError('日期格式無效')
    if len(text) == 7:
        text = str(int(text[:3]) + 1911) + text[3:]
    return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()


def _number(value: Any, *, integer: bool = True, nonnegative: bool = False) -> Any:
    text = str(value).strip()
    if not _NUMBER.fullmatch(text):
        raise ValueError('缺少或無效的數值')
    number = Decimal(text.replace(',', ''))
    if nonnegative and number < 0:
        raise ValueError('數值不可為負')
    if integer:
        if number != number.to_integral_value():
            raise ValueError('家數或金額不是整數')
        return int(number)
    result = float(number)
    if not math.isfinite(result):
        raise ValueError('數值不是有限值')
    return result


def _table_rows(table: Any) -> List[Dict[str, Any]]:
    if not isinstance(table, dict):
        raise ValueError('資料表格式無效')
    fields, rows = table.get('fields'), table.get('data')
    if (not isinstance(fields, list) or not fields
            or not all(isinstance(field, str) for field in fields)
            or len(set(fields)) != len(fields) or not isinstance(rows, list) or not rows):
        raise ValueError('缺少資料或欄位名稱')
    if any(not isinstance(row, list) or len(row) != len(fields) for row in rows):
        raise ValueError('資料與欄位數量不符')
    return [dict(zip(fields, row)) for row in rows]


def _twse_report(payload: Any, target: str) -> dict:
    if not isinstance(payload, dict) or payload.get('stat') != 'OK':
        raise ValueError('官方回應無資料')
    actual = _date(payload.get('date'))
    if actual != target:
        raise ValueError(f'日期不符：要求 {target}，來源 {actual}')
    return payload


def _tpex_rows(payload: Any, target: str) -> List[dict]:
    if not isinstance(payload, list) or not payload:
        raise ValueError('官方回應無資料')
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError('官方資料列格式無效')
        actual = _date(row.get('Date'))
        if actual != target:
            raise ValueError(f'日期不符：要求 {target}，來源 {actual}')
    return payload


def _named(rows: List[dict], key: str) -> Dict[str, dict]:
    result = {}
    for row in rows:
        name = row[key]
        if not isinstance(name, str) or not name.strip() or name.strip() in result:
            raise ValueError('缺少或重複的資料名稱')
        result[name.strip()] = row
    return result


def _money_row(name: str, row: dict, columns: tuple) -> dict:
    buy = _number(row[columns[0]], nonnegative=True)
    sell = _number(row[columns[1]], nonnegative=True)
    net = _number(row[columns[2]])
    if buy - sell != net:
        raise ValueError('法人買賣金額與買賣超不一致')
    return {'name': name, 'buy': buy, 'sell': sell, 'net': net}


def _institutions(rows: List[dict], target: str, url: str, universe: str) -> dict:
    for key in ('buy', 'sell', 'net'):
        if sum(row[key] for row in rows[:3]) != rows[3][key]:
            raise ValueError('三大法人金額與官方合計不一致')
    return {'trade_date': target, 'unit': 'TWD', 'rows': rows,
            'source_url': url, 'universe': universe}


def _twse_institutions(payload: Any, target: str, url: str) -> dict:
    report = _twse_report(payload, target)
    if report.get('hints') != '單位：元':
        raise ValueError('法人金額單位無法確認為元')
    named = _named(_table_rows(report), '單位名稱')
    columns = ('買進金額', '賣出金額', '買賣差額')
    dealer_parts = [_money_row(name, named[name], columns)
                    for name in ('自營商(自行買賣)', '自營商(避險)')]
    dealer = {'name': '自營商合計', **{
        key: sum(row[key] for row in dealer_parts) for key in ('buy', 'sell', 'net')
    }}
    rows = [_money_row('外資及陸資(不含自營商)', named['外資及陸資(不含外資自營商)'], columns),
            _money_row('投信', named['投信'], columns), dealer,
            _money_row('三大法人合計', named['合計'], columns)]
    return _institutions(rows, target, url,
                         'TWSE 三大法人金額統計；外資自營商已計入自營商，不重複加總')


def _tpex_institutions(payload: Any, target: str, url: str) -> dict:
    named = _named(_tpex_rows(payload, target), 'Investor')
    columns = ('PurchaseAmount', 'SaleAmount', 'Net')
    rows = [_money_row(name, named[name], columns) for name in
            ('外資及陸資(不含自營商)', '投信', '自營商合計', '三大法人合計*')]
    rows[-1]['name'] = '三大法人合計'
    # 元：官方 /www/zh-tw/insti/summary 的「買進金額(元)」已實際核對。
    return _institutions(rows, target, url,
                         'TPEx 上櫃股票；含等價、零股、盤後定價，不含鉅額、標購、加掛 ETF')


def _twse_table(payload: Any, target: str, title: str) -> List[dict]:
    report = _twse_report(payload, target)
    tables = report.get('tables')
    if not isinstance(tables, list):
        raise ValueError('缺少官方資料表')
    matching = [table for table in tables if isinstance(table, dict)
                and isinstance(table.get('title'), str) and table['title'].endswith(title)]
    if len(matching) != 1:
        raise ValueError('找不到唯一的官方資料表')
    return _table_rows(matching[0])


def _twse_breadth(payload: Any, target: str, url: str) -> dict:
    named = _named(_twse_table(payload, target, '漲跌證券數合計'), '類型')
    values = {}
    for key, label in (('up', '上漲(漲停)'), ('down', '下跌(跌停)')):
        text = str(named[label]['股票']).strip()
        match = re.fullmatch(r'([\d,]+)\(([\d,]+)\)', text)
        if not match:
            raise ValueError('漲跌家數格式無效')
        values[key] = _number(match[1], nonnegative=True)
        values['limit_' + key] = _number(match[2], nonnegative=True)
        if values['limit_' + key] > values[key]:
            raise ValueError('漲跌停家數大於漲跌家數')
    values.update({key: _number(named[label]['股票'], nonnegative=True)
                   for key, label in (('flat', '持平'), ('untraded', '未成交'), ('no_comparison', '無比價'))})
    return {'trade_date': target, 'unit': 'stocks', **values,
            'universe': 'TWSE 官方漲跌證券數合計之股票欄', 'source_url': url}


def _tpex_breadth(payload: Any, target: str, url: str) -> dict:
    rows = _tpex_rows(payload, target)
    if len(rows) != 1:
        raise ValueError('股票市場現況不是唯一的每日統計')
    row = rows[0]
    values = {key: _number(row[column], nonnegative=True) for key, column in (
        ('up', 'PriceRiseCompanyNumbers'), ('down', 'PriceDeclineCompanyNumbers'),
        ('flat', 'PriceFlatCompanyNumbers'), ('limit_up', 'LimitUpCompanyNumbers'),
        ('limit_down', 'LimitDownCompanyNumbers'),
        ('untraded', 'UnmatchedCompanyNumbersSuspensionStocksIncluded'),
        ('listed', 'ListedCompanyNumbers'),
    )}
    if sum(values[key] for key in ('up', 'down', 'flat', 'untraded')) != values['listed']:
        raise ValueError('上櫃股票漲跌平盤與未成交家數不等於上櫃家數')
    if values['limit_up'] > values['up'] or values['limit_down'] > values['down']:
        raise ValueError('漲跌停家數大於漲跌家數')
    return {'trade_date': target, 'unit': 'stocks', **values, 'no_comparison': None,
            'universe': 'TPEx 官方上櫃股票市場現況；未成交含暫停交易', 'source_url': url}


def _twse_sectors(payload: Any, target: str, url: str) -> dict:
    named = _named(_twse_table(payload, target, '價格指數(臺灣證券交易所)'), '指數')
    rows = []
    for name, row in named.items():
        if name.endswith('類指數'):
            rows.append({'name': name, 'change_pct': _number(row['漲跌百分比(%)'], integer=False)})
    if not rows:
        raise ValueError('缺少官方類股價格指數')
    return {'trade_date': target, 'unit': 'percent', 'rows': rows,
            'basis': 'official_price_index', 'source_url': url}


def _tpex_sectors(payload: Any, target: str, url: str) -> dict:
    if not isinstance(payload, dict) or payload.get('stat') != 'ok':
        raise ValueError('官方回應無資料')
    actual = _date(payload.get('date'))
    if actual != target:
        raise ValueError(f'日期不符：要求 {target}，來源 {actual}')
    tables = payload.get('tables')
    if not isinstance(tables, list):
        raise ValueError('缺少官方資料表')
    matching = [table for table in tables if isinstance(table, dict)
                and table.get('title') == '上櫃股價指數收盤行情']
    if len(matching) != 1:
        raise ValueError('找不到唯一的官方價格指數資料表')
    table = matching[0]
    if _date(table.get('date')) != target:
        raise ValueError('價格指數資料表日期不符')
    named = _named(_table_rows(table), '指數')
    if _number(table.get('totalCount'), nonnegative=True) != len(named):
        raise ValueError('官方價格指數資料表不完整')
    if not _TPEX_SECTOR_NAMES.issubset(named):
        raise ValueError('缺少已核對的官方產業分類價格指數')
    rows = [{'name': name, 'change_pct': _number(row['漲跌幅度(%)'], integer=False)}
            for name, row in named.items() if name in _TPEX_SECTOR_NAMES]
    return {'trade_date': target, 'unit': 'percent', 'rows': rows,
            'basis': 'official_price_index', 'source_url': url}


def get_tw_market_supplements(trade_date: str) -> dict:
    """取得指定日的官方市場補充資料；失敗項目為 None 並附原因。

    trade_date 支援 YYYY-MM-DD、YYYYMMDD；回傳日期統一為 YYYY-MM-DD。
    TPEx 法人與家數來源沒有歷史日期參數，日期不符即缺失。
    函式不觸發 LLM 或通知。
    """
    result = {'trade_date': trade_date, 'markets': {
        market: {'institutions': None, 'breadth': None, 'sectors': None, 'missing_reasons': {}}
        for market in ('twse', 'tpex')
    }}
    try:
        target = _date(trade_date)
    except (TypeError, ValueError):
        for market in result['markets'].values():
            market['missing_reasons'] = {key: '要求的交易日期無效' for key in ('institutions', 'breadth', 'sectors')}
        return result
    result['trade_date'] = target
    compact = target.replace('-', '')
    sources = (
        ('twse', 'institutions', _TWSE_INSTITUTIONS,
         {'response': 'json', 'dayDate': compact, 'type': 'day'}, _twse_institutions),
        ('twse', 'breadth', _TWSE_MARKET,
         {'response': 'json', 'date': compact, 'type': 'MS'}, _twse_breadth),
        ('twse', 'sectors', _TWSE_MARKET,
         {'response': 'json', 'date': compact, 'type': 'IND'}, _twse_sectors),
        ('tpex', 'institutions', _TPEX_INSTITUTIONS, None, _tpex_institutions),
        ('tpex', 'breadth', _TPEX_BREADTH, None, _tpex_breadth),
        ('tpex', 'sectors', _TPEX_SECTORS,
         {'date': target.replace('-', '/'), 'response': 'json'}, _tpex_sectors),
    )
    for market, kind, url, params, parse in sources:
        source_url = requests.Request('GET', url, params=params).prepare().url
        try:
            response = requests.get(url, params=params, timeout=(5, 15), allow_redirects=False)
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise ValueError('官方來源重新導向，未取用未確認來源')
            result['markets'][market][kind] = parse(response.json(), target, source_url)
        except (requests.RequestException, KeyError, TypeError, ValueError, OverflowError) as exc:
            reason = f'{type(exc).__name__}: {exc}'
            result['markets'][market]['missing_reasons'][kind] = reason
            logger.warning('[台股總覽] %s %s 補充資料缺失：%s', market, kind, reason)
    return result

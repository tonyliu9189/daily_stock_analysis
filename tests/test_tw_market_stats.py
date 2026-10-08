# -*- coding: utf-8 -*-
"""Official response shapes; deterministic tests never access the network."""

from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest
import requests

from data_provider.taiwan_market_stats import get_tw_market_supplements


DAY = '2026-10-07'

# BFI82U / MI_INDEX fixtures use the 2026-10-07 live response fields.
TWSE_INSTITUTIONS = {
    'stat': 'OK', 'date': '20261007', 'hints': '單位：元',
    'fields': ['單位名稱', '買進金額', '賣出金額', '買賣差額'],
    'data': [
        ['自營商(自行買賣)', '8,798,053,626', '10,165,473,556', '-1,367,419,930'],
        ['自營商(避險)', '23,287,779,984', '29,716,816,672', '-6,429,036,688'],
        ['投信', '21,947,419,403', '25,270,803,488', '-3,323,384,085'],
        ['外資及陸資(不含外資自營商)', '330,798,361,443', '343,842,247,808', '-13,043,886,365'],
        # Foreign dealers are already included in dealers; do not add again.
        ['外資自營商', '100', '50', '50'],
        ['合計', '384,831,614,456', '408,995,341,524', '-24,163,727,068'],
    ],
}
TWSE_BREADTH = {
    'stat': 'OK', 'date': '20261007',
    'tables': [{}, {
        'title': '漲跌證券數合計', 'fields': ['類型', '整體市場', '股票'],
        'data': [['上漲(漲停)', '7,322(117)', '588(12)'],
                 ['下跌(跌停)', '7,537(74)', '387(4)'],
                 ['持平', '1,222', '99'], ['未成交', '17,062', '5'], ['無比價', '3,498', '3']],
    }],
}
TWSE_SECTORS = {
    'stat': 'OK', 'date': '20261007', 'tables': [{
        'title': '115年10月07日 價格指數(臺灣證券交易所)',
        'fields': ['指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記'],
        'data': [['發行量加權股價指數', '49,806.37', '-', '16.18', '-0.03', ''],
                 ['半導體類指數', '1,677.95', "<p style='color:green'>-</p>", '3.95', '-0.23', ''],
                 ['金融保險類指數', '3,595.85', '+', '36.34', '1.02', '']],
    }, {
        'title': '價格指數(跨市場)',
        'fields': ['指數', '漲跌百分比(%)'], 'data': [['跨市場半導體類指數', '99']],
    }, {
        'title': '報酬指數(臺灣證券交易所)',
        'fields': ['報酬指數', '漲跌百分比(%)'], 'data': [['半導體類指數', '88']],
    }],
}

# TPEx field names / category labels are from the live 2026-10-08 OpenAPI;
# amounts here are small synthetic values for exact integer arithmetic checks.
TPEX_INSTITUTIONS = [
    {'Date': '1151007', 'Investor': '外資及陸資合計', 'PurchaseAmount': '1250', 'SaleAmount': '800', 'Net': '450'},
    {'Date': '1151007', 'Investor': '　外資及陸資(不含自營商)',
     'PurchaseAmount': '1200', 'SaleAmount': '800', 'Net': '400'},
    {'Date': '1151007', 'Investor': '　外資自營商', 'PurchaseAmount': '50', 'SaleAmount': '0', 'Net': '50'},
    {'Date': '1151007', 'Investor': '投信', 'PurchaseAmount': '200', 'SaleAmount': '300', 'Net': '-100'},
    {'Date': '1151007', 'Investor': '自營商合計', 'PurchaseAmount': '500', 'SaleAmount': '500', 'Net': '0'},
    {'Date': '1151007', 'Investor': '三大法人合計*', 'PurchaseAmount': '1900', 'SaleAmount': '1600', 'Net': '300'},
]
TPEX_BREADTH = [{
    'Date': '1151007', 'ListedCompanyNumbers': '893',
    'PriceRiseCompanyNumbers': '356', 'LimitUpCompanyNumbers': '23',
    'PriceDeclineCompanyNumbers': '416', 'LimitDownCompanyNumbers': '3',
    'PriceFlatCompanyNumbers': '95', 'UnmatchedCompanyNumbersSuspensionStocksIncluded': '26',
}]
TPEX_SECTORS = {
    'stat': 'ok', 'date': '20261007', 'tables': [{
        'title': '上櫃股價指數收盤行情', 'date': '115/10/07', 'totalCount': 25,
        'fields': ['指數', '收市指數', '漲跌', '漲跌幅度(%)', '大盤資訊連結'],
        'data': [['櫃買指數', '426.71', '-3.75', '-0.87', 'https://example.test/'],
                 ['富櫃200指數', '19,835.43', '-188.57', '-0.94', ''],
                 ['TPEx FactSet半導體氣候韌性指數', '19,578.70', '-324.29', '-1.63', '']] + [
            [name, '100', '-1', '-0.99', ''] for name in (
                '紡織纖維', '電機機械', '鋼鐵工業', '電子工業', '建材營造', '航運業', '觀光餐旅', '其他',
                '化學工業', '生技醫療', '半導體業', '電腦及週邊設備業', '光電業', '通信網路業',
                '電子零組件業', '電子通路業', '資訊服務業', '其他電子業', '文化創意業', '綠能環保', '數位雲端', '居家生活',
            )
        ],
    }, {
        'title': '', 'date': '115/10/07', 'totalCount': 1,
        'fields': ['報酬指數', '收市指數', '漲跌', '漲跌幅度(%)', '大盤資訊連結'],
        'data': [['半導體業', '999', '99', '99', '']],
    }],
}


def payloads():
    return deepcopy([TWSE_INSTITUTIONS, TWSE_BREADTH, TWSE_SECTORS,
                     TPEX_INSTITUTIONS, TPEX_BREADTH, TPEX_SECTORS])


def response(payload, status=200):
    result = MagicMock()
    result.status_code = status
    result.json.return_value = payload
    return result


def run(fixtures=None, day=DAY):
    fixtures = fixtures if fixtures is not None else payloads()
    with patch('data_provider.taiwan_market_stats.requests.get',
               side_effect=[response(item) if not isinstance(item, Exception) else item for item in fixtures]) as get:
        result = get_tw_market_supplements(day)
    return result, get


def test_official_units_totals_counts_indices_and_bounded_requests():
    result, get = run()
    assert result['trade_date'] == DAY
    twse, tpex = (result['markets'][key] for key in ('twse', 'tpex'))
    for market in (twse, tpex):
        institutions = market['institutions']
        assert institutions['unit'] == 'TWD'
        assert len(institutions['rows']) == 4
        assert institutions['rows'][2]['name'] == '自營商合計'
        assert institutions['rows'][3]['name'] == '三大法人合計'
        for key in ('buy', 'sell', 'net'):
            assert sum(row[key] for row in institutions['rows'][:3]) == institutions['rows'][3][key]
        for key in ('institutions', 'breadth'):
            assert market[key]['trade_date'] == DAY
            assert market[key]['source_url'].startswith('https://')
    assert twse['institutions']['rows'][-1]['net'] == -24163727068
    assert tpex['institutions']['rows'][2]['net'] == 0
    assert tpex['institutions']['rows'][-1]['net'] == 300
    assert twse['breadth']['unit'] == 'stocks'
    assert (twse['breadth']['up'], twse['breadth']['down'], twse['breadth']['flat']) == (588, 387, 99)
    assert (twse['breadth']['limit_up'], twse['breadth']['limit_down']) == (12, 4)
    assert twse['breadth']['no_comparison'] == 3
    assert '股票欄' in twse['breadth']['universe']
    assert tpex['breadth']['listed'] == 893
    assert tpex['breadth']['untraded'] == 26
    assert tpex['breadth']['no_comparison'] is None
    assert twse['sectors']['rows'] == [
        {'name': '半導體類指數', 'change_pct': -0.23},
        {'name': '金融保險類指數', 'change_pct': 1.02},
    ]
    assert twse['sectors']['basis'] == 'official_price_index'
    assert twse['sectors']['unit'] == 'percent'
    assert len(tpex['sectors']['rows']) == 22
    assert {'name': '半導體業', 'change_pct': -0.99} in tpex['sectors']['rows']
    assert tpex['sectors']['basis'] == 'official_price_index'
    assert tpex['sectors']['unit'] == 'percent'
    assert tpex['missing_reasons'] == {}
    assert twse['missing_reasons'] == {}
    assert get.call_count == 6
    assert get.call_args_list[0].kwargs['params'] == {'response': 'json', 'dayDate': '20261007', 'type': 'day'}
    assert 'dayDate=20261007' in twse['institutions']['source_url']
    assert get.call_args_list[1].kwargs['params']['type'] == 'MS'
    assert get.call_args_list[2].kwargs['params']['type'] == 'IND'
    assert get.call_args_list[5].kwargs['params'] == {'date': '2026/10/07', 'response': 'json'}
    for call in get.call_args_list:
        assert call.kwargs['timeout'] == (5, 15)
        assert call.kwargs['allow_redirects'] is False


@pytest.mark.parametrize('index,market,kind', [
    (0, 'twse', 'institutions'), (1, 'twse', 'breadth'), (2, 'twse', 'sectors'),
    (3, 'tpex', 'institutions'), (4, 'tpex', 'breadth'),
    (5, 'tpex', 'sectors'),
])
@pytest.mark.parametrize('wrong_day', ['20261006', '20261008'])
def test_stale_and_future_dates_are_missing_independently(index, market, kind, wrong_day):
    fixtures = payloads()
    if index < 3 or index == 5:
        fixtures[index]['date'] = wrong_day
    else:
        for row in fixtures[index]:
            row['Date'] = '115' + wrong_day[4:]
    result, get = run(fixtures)
    assert result['markets'][market][kind] is None
    assert '日期不符' in result['markets'][market]['missing_reasons'][kind]
    assert get.call_count == 6
    other = 'tpex' if market == 'twse' else 'twse'
    assert result['markets'][other]['institutions'] is not None


def test_mixed_tpex_row_dates_cannot_form_a_daily_total():
    fixtures = payloads()
    fixtures[3][3]['Date'] = '1151006'
    result, _ = run(fixtures)
    assert result['markets']['tpex']['institutions'] is None
    assert result['markets']['tpex']['breadth'] is not None


@pytest.mark.parametrize('index,market,kind', [
    (0, 'twse', 'institutions'), (1, 'twse', 'breadth'), (2, 'twse', 'sectors'),
    (3, 'tpex', 'institutions'), (4, 'tpex', 'breadth'),
    (5, 'tpex', 'sectors'),
])
@pytest.mark.parametrize('empty', [None, {}, [], {'stat': '沒有符合條件的資料'}])
def test_missing_payload_never_becomes_zero(index, market, kind, empty):
    fixtures = payloads()
    fixtures[index] = empty
    result, _ = run(fixtures)
    assert result['markets'][market][kind] is None
    assert kind in result['markets'][market]['missing_reasons']


@pytest.mark.parametrize('bad', ['', '--', None, 'NaN', 'inf', 'abc', '1,2', '1.5', True])
def test_bad_money_does_not_truncate_or_become_zero(bad):
    fixtures = payloads()
    fixtures[0]['data'][2][3] = bad
    fixtures[3][3]['Net'] = bad
    result, _ = run(fixtures)
    for market in ('twse', 'tpex'):
        assert result['markets'][market]['institutions'] is None
        assert result['markets'][market]['breadth'] is not None


@pytest.mark.parametrize('bad', ['', '--', None, 'NaN', '-1', '1.5', 'abc'])
def test_bad_breadth_counts_do_not_become_flat_or_zero(bad):
    fixtures = payloads()
    fixtures[1]['tables'][1]['data'][2][2] = bad
    fixtures[4][0]['PriceFlatCompanyNumbers'] = bad
    result, _ = run(fixtures)
    assert result['markets']['twse']['breadth'] is None
    assert result['markets']['tpex']['breadth'] is None


@pytest.mark.parametrize('bad', ['', '--', None, 'NaN', 'inf', 'abc'])
def test_missing_or_nonfinite_sector_percentage_does_not_become_zero(bad):
    fixtures = payloads()
    fixtures[2]['tables'][0]['data'][1][4] = bad
    fixtures[5]['tables'][0]['data'][3][3] = bad
    result, _ = run(fixtures)
    assert result['markets']['twse']['sectors'] is None
    assert result['markets']['tpex']['sectors'] is None
    assert result['markets']['twse']['breadth'] is not None


@pytest.mark.parametrize('unit', [None, '單位：千元', '單位：股'])
def test_unverified_money_units_are_rejected(unit):
    fixtures = payloads()
    fixtures[0]['hints'] = unit
    result, _ = run(fixtures)
    assert result['markets']['twse']['institutions'] is None


def test_real_zero_counts_and_zero_sector_change_are_preserved():
    fixtures = payloads()
    fixtures[1]['tables'][1]['data'][2][2] = '0'
    fixtures[4][0].update(PriceFlatCompanyNumbers='0', ListedCompanyNumbers='798')
    fixtures[2]['tables'][0]['data'][1][4] = '0.00'
    result, _ = run(fixtures)
    assert result['markets']['twse']['breadth']['flat'] == 0
    assert result['markets']['tpex']['breadth']['flat'] == 0
    assert result['markets']['twse']['sectors']['rows'][0]['change_pct'] == 0.0


def test_missing_renamed_fields_are_explicit_and_column_reordering_is_safe():
    fixtures = payloads()
    for table in (fixtures[0], fixtures[1]['tables'][1], fixtures[2]['tables'][0]):
        table['fields'].reverse()
        for row in table['data']:
            row.reverse()
    reordered, _ = run(fixtures)
    assert reordered['markets']['twse']['institutions']['rows'][-1]['net'] == -24163727068
    assert reordered['markets']['twse']['breadth']['up'] == 588
    assert reordered['markets']['twse']['sectors']['rows'][0]['change_pct'] == -0.23
    fixtures = payloads()
    fixtures[0]['fields'][3] = '買賣超股數'
    fixtures[1]['tables'][1]['fields'][2] = '股票_v2'
    fixtures[2]['tables'][0]['fields'][4] = '漲跌點數_v2'
    del fixtures[3][3]['Net']
    del fixtures[4][0]['PriceFlatCompanyNumbers']
    result, _ = run(fixtures)
    assert all(result['markets']['twse'][kind] is None for kind in ('institutions', 'breadth', 'sectors'))
    assert result['markets']['tpex']['institutions'] is None
    assert result['markets']['tpex']['breadth'] is None


def test_invalid_totals_and_limit_subsets_are_rejected():
    fixtures = payloads()
    fixtures[0]['data'][5][1] = '384,831,614,457'
    fixtures[3][-1]['PurchaseAmount'] = '1901'
    fixtures[3][-1]['Net'] = '301'
    fixtures[1]['tables'][1]['data'][0][2] = '588(589)'
    fixtures[4][0]['ListedCompanyNumbers'] = '894'
    result, _ = run(fixtures)
    for market in ('twse', 'tpex'):
        assert result['markets'][market]['institutions'] is None
        assert result['markets'][market]['breadth'] is None


@pytest.mark.parametrize('bad_date', ['', '2026-02-30', '202610', 'garbage', None])
def test_bad_target_date_returns_explicit_missing_without_requests(bad_date):
    with patch('data_provider.taiwan_market_stats.requests.get') as get:
        result = get_tw_market_supplements(bad_date)
    get.assert_not_called()
    for market in result['markets'].values():
        assert all(market[kind] is None for kind in ('institutions', 'breadth', 'sectors'))
        assert len(market['missing_reasons']) == 3


@pytest.mark.parametrize('bad_date', [None, '1150230', 'invalid'])
def test_undated_or_invalid_source_dates_are_not_attributed_to_target(bad_date):
    fixtures = payloads()
    for report in fixtures[:3]:
        report['date'] = bad_date
    for rows in fixtures[3:5]:
        rows[0]['Date'] = bad_date
    fixtures[5]['date'] = bad_date
    result, _ = run(fixtures)
    assert all(result['markets']['twse'][kind] is None for kind in ('institutions', 'breadth', 'sectors'))
    assert result['markets']['tpex']['institutions'] is None
    assert result['markets']['tpex']['breadth'] is None
    assert result['markets']['tpex']['sectors'] is None


def test_compact_date_and_minguo_source_dates_normalize_to_iso():
    result, _ = run(day='20261007')
    assert result['trade_date'] == DAY
    assert result['markets']['tpex']['institutions']['trade_date'] == DAY


def test_timeout_json_errors_http_errors_and_redirects_fail_independently():
    bad_json = response(None)
    bad_json.json.side_effect = ValueError('not JSON')
    bad_http = response(None, 429)
    bad_http.raise_for_status.side_effect = requests.HTTPError('429')
    responses = [requests.Timeout('timeout'), bad_json, bad_http,
                 response(TPEX_INSTITUTIONS, 302), response(TPEX_BREADTH), response(TPEX_SECTORS)]
    with patch('data_provider.taiwan_market_stats.requests.get', side_effect=responses) as get:
        result = get_tw_market_supplements(DAY)
    assert get.call_count == 6
    assert all(result['markets']['twse'][kind] is None for kind in ('institutions', 'breadth', 'sectors'))
    assert result['markets']['tpex']['institutions'] is None
    assert result['markets']['tpex']['breadth']['up'] == 356
    assert len(result['markets']['tpex']['sectors']['rows']) == 22


@pytest.mark.parametrize('mutation', ['short_row', 'duplicate_field', 'duplicate_category', 'duplicate_table'])
def test_malformed_or_ambiguous_tables_are_rejected(mutation):
    fixtures = payloads()
    if mutation == 'short_row':
        fixtures[0]['data'][0].pop()
    elif mutation == 'duplicate_field':
        fixtures[0]['fields'][3] = fixtures[0]['fields'][2]
    elif mutation == 'duplicate_category':
        fixtures[0]['data'].append(fixtures[0]['data'][2])
    else:
        fixtures[1]['tables'].append(fixtures[1]['tables'][1])
    result, _ = run(fixtures)
    kind = 'breadth' if mutation == 'duplicate_table' else 'institutions'
    assert result['markets']['twse'][kind] is None


@pytest.mark.parametrize('mutation', ['stale_table', 'incomplete_count', 'missing_sector', 'duplicate_table'])
def test_tpex_sector_date_completeness_and_price_table_are_required(mutation):
    fixtures = payloads()
    table = fixtures[5]['tables'][0]
    if mutation == 'stale_table':
        table['date'] = '115/10/06'
    elif mutation == 'incomplete_count':
        table['totalCount'] = 99
    elif mutation == 'missing_sector':
        table['data'].pop()
        table['totalCount'] -= 1
    else:
        fixtures[5]['tables'].append(table)
    result, _ = run(fixtures)
    assert result['markets']['tpex']['sectors'] is None
    assert 'sectors' in result['markets']['tpex']['missing_reasons']
    assert result['markets']['tpex']['institutions'] is not None

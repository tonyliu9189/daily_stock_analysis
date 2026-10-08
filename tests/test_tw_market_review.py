# -*- coding: utf-8 -*-
"""台股市場總覽的資料、地區、交易日及報告回歸測試。"""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from data_provider.base import DataFetcherManager
from data_provider.taiwan_market import get_tw_market_indices
from src.config import Config
from src.core.market_review import run_market_review
from src.core.trading_calendar import compute_effective_region
from src.market_analyzer import MarketAnalyzer
from src.services.daily_market_context import DailyMarketContextService, format_daily_market_context_prompt_section
from src.utils.market_review_region import normalize_market_review_region_strict


TWSE_ROW = {'Date': '1151007', 'TradeVolume': '10357959027',
            'TradeValue': '986280041197', 'TAIEX': '49806.37', 'Change': '-16.18'}
TPEX_ROW = {'Date': '1151007', 'TradeVolume': '1220344663',
            'TradeAmount': '297728502045', 'TPExIndex': '430.46', 'Change': '-0.40'}


def response(rows):
    result = MagicMock()
    result.json.return_value = rows
    return result


def tw_analyzer(language='zh'):
    config = SimpleNamespace(report_language=language, market_review_region='tw',
                             market_review_color_scheme='red_up')
    with patch('src.market_analyzer.DataFetcherManager'):
        return MarketAnalyzer(region='tw', config=config)


def test_official_daily_data_normalizes_dates_units_and_actual_changes():
    with patch('data_provider.taiwan_market.get_effective_trading_date', return_value=date(2026, 10, 7)), \
         patch('data_provider.taiwan_market.requests.get', side_effect=[
             response([dict(TWSE_ROW, Date='1151008', TAIEX='99999'), TWSE_ROW]), response([TPEX_ROW]),
         ]) as get:
        items = get_tw_market_indices()
    assert [item['code'] for item in items] == ['TWII', 'TWOII']
    assert all(item['trade_date'] == '2026-10-07' for item in items)
    assert items[0]['current'] == 49806.37
    assert items[0]['change_pct'] == pytest.approx(-16.18 / 49822.55 * 100)
    assert items[0]['volume'] == 10357959027
    assert items[0]['amount'] == 986280041197
    assert items[1]['source'] == 'TPEx'
    assert all(call.kwargs['timeout'] == (5, 15) for call in get.call_args_list)


def test_official_daily_data_does_not_mix_dates():
    with patch('data_provider.taiwan_market.get_effective_trading_date', return_value=date(2026, 10, 7)), \
         patch('data_provider.taiwan_market.requests.get', side_effect=[
             response([TWSE_ROW]), response([dict(TPEX_ROW, Date='1151006')]),
         ]):
        assert [item['code'] for item in get_tw_market_indices()] == ['TWII']


@pytest.mark.parametrize('bad_rows', [[], {'error': 'unavailable'},
                                     [dict(TWSE_ROW, TAIEX='NaN')],
                                     [dict(TWSE_ROW, Date='invalid')]])
def test_invalid_official_data_is_not_presented_as_a_zero_quote(bad_rows):
    with patch('data_provider.taiwan_market.get_effective_trading_date', return_value=date(2026, 10, 7)), \
         patch('data_provider.taiwan_market.requests.get', side_effect=[response(bad_rows), response([])]):
        assert get_tw_market_indices() == []


def test_tw_route_never_uses_chinese_fetcher_even_if_it_offers_data():
    cn_fetcher = MagicMock(name='CN')
    cn_fetcher.name = 'EfinanceFetcher'
    manager = DataFetcherManager(fetchers=[cn_fetcher])
    with patch('data_provider.taiwan_market.requests.get', side_effect=requests.Timeout('timeout')):
        assert manager.get_main_indices('tw') == []
    cn_fetcher.get_main_indices.assert_not_called()


def test_tw_region_and_calendar_do_not_fall_back_to_china():
    assert Config._parse_market_review_region('TW') == 'tw'
    assert normalize_market_review_region_strict(' tw,us ') == 'us,tw'
    assert compute_effective_region('tw', {'tw'}) == 'tw'
    assert compute_effective_region('tw', {'cn'}) == ''
    assert compute_effective_region('both', {'tw'}) == 'tw'


def test_tw_market_context_uses_taiwan_labels_and_calendar():
    import main

    with patch('src.core.trading_calendar.get_effective_trading_date', return_value=date(2026, 10, 7)) as get:
        assert main._resolve_daily_market_context_target_date(
            'tw', datetime(2026, 10, 7, 17, 20, tzinfo=timezone.utc),
        ) == date(2026, 10, 7)
    assert get.call_args.args == ('tw',)
    text = format_daily_market_context_prompt_section({
        'region': 'tw', 'trade_date': '2026-10-07', 'summary': '台灣市場觀察',
    })
    assert '台股（tw）' in text
    assert 'A股（cn）' not in text


def test_tw_overview_prompt_and_template_use_official_data_and_actual_trade_date():
    analyzer = tw_analyzer()
    with patch('data_provider.taiwan_market.get_effective_trading_date', return_value=date(2026, 10, 7)), \
         patch('data_provider.taiwan_market.requests.get', side_effect=[response([TWSE_ROW]), response([TPEX_ROW])]):
        analyzer.data_manager.get_main_indices.return_value = get_tw_market_indices()
    overview = analyzer.get_market_overview()
    assert overview.date == '2026-10-07'
    analyzer.data_manager.get_market_stats.assert_not_called()
    analyzer.data_manager.get_sector_rankings.assert_not_called()
    prompt = analyzer._build_review_prompt(overview, [])
    report = analyzer._generate_template_review(overview, [])
    for text in (prompt, report):
        assert '台股' in text and '櫃買指數' in text
        assert '9862.80' in text.replace(',', '')
        assert '新臺幣億元' in text
        assert '上证' not in text and '北向' not in text
    assert '台灣繁體中文' in prompt
    assert '2026-10-07 台股市場總覽' in report
    assert analyzer._supports_market_light() is False
    payload = analyzer.build_market_review_payload(overview, [], report)
    assert payload['region'] == 'tw'
    assert payload['indices'][0]['amount_currency'] == 'TWD'
    assert payload['indices'][0]['volume_unit'] == 'shares'
    assert not {'open', 'high', 'low', 'amplitude'} & payload['indices'][0].keys()
    assert 'breadth' not in payload and 'market_light' not in payload
    injected = analyzer._inject_data_into_review('## 台股市場總覽\n### 二、指數結構\n指數分歧。', overview)
    assert '成交金額（新臺幣億元）' in injected


def test_run_tw_market_review_keeps_region_in_report_and_structured_history():
    analyzer = tw_analyzer()
    with patch('data_provider.taiwan_market.get_effective_trading_date', return_value=date(2026, 10, 7)), \
         patch('data_provider.taiwan_market.requests.get', side_effect=[response([TWSE_ROW]), response([TPEX_ROW])]):
        analyzer.data_manager.get_main_indices.return_value = get_tw_market_indices()
    with patch('src.core.market_review.MarketAnalyzer', return_value=analyzer) as factory, \
         patch.object(analyzer, 'search_market_news', return_value=[]), \
         patch.object(analyzer, '_merge_persisted_market_intelligence', side_effect=lambda news: news):
        result = run_market_review(MagicMock(), config=analyzer.config, send_notification=False,
                                   save_report_file=False, persist_history=False, return_structured=True)
    assert factory.call_args.kwargs['region'] == 'tw'
    assert result.market_review_payload['region'] == 'tw'
    assert '台股市場總覽' in result.report


def test_tw_english_title_and_prompt_do_not_use_a_share_market():
    analyzer = tw_analyzer('en')
    assert analyzer._get_review_title('2026-10-07') == '## 2026-10-07 Taiwan Market Recap'
    assert 'TAIEX' in analyzer._get_index_hint()
    assert analyzer._get_turnover_unit_label() == 'TWD 100m'


def test_tw_news_search_passes_taiwan_context_to_search_service():
    analyzer = tw_analyzer()
    analyzer.search_service = MagicMock()
    analyzer.search_service.search_stock_news.return_value = SimpleNamespace(results=[])
    analyzer.search_market_news()
    calls = analyzer.search_service.search_stock_news.call_args_list
    assert len(calls) == 3
    assert all(call.kwargs['stock_name'] == '台灣股市' for call in calls)
    assert all('台' in ' '.join(call.kwargs['focus_keywords']) for call in calls)


def test_tw_context_does_not_reuse_missing_or_empty_tw_child_in_mixed_history():
    service = DailyMarketContextService(db_manager=MagicMock())
    for payload in (
        {'region': 'cn,tw', 'markets': {'cn': {'region': 'cn', 'summary': '中國市場'}}},
        {'region': 'cn,tw', 'summary': '中國市場總結'},
        {'region': 'cn,tw', 'markets': {'tw': {'region': 'tw'}}},
    ):
        context = service._build_context_from_payload(
            region='tw', trade_date=date(2026, 10, 7), payload=payload,
            source='analysis_history', fallback_summary='中國市場總結',
        )
        assert context is None
    context = service._build_context_from_payload(
        region='tw', trade_date=date(2026, 10, 7), source='analysis_history',
        payload={'region': 'cn,tw', 'markets': {'tw': {
            'region': 'tw', 'date': '2026-10-07', 'summary': '台灣市場摘要',
        }}}, fallback_summary='中國市場總結',
    )
    assert context.summary == '台灣市場摘要'


def test_tw_context_rejects_stale_trade_date_in_same_query():
    service = DailyMarketContextService(db_manager=MagicMock())
    assert service._build_context_from_payload(
        region='tw', trade_date=date(2026, 10, 7), source='market_review_runtime',
        payload={'region': 'tw', 'date': '2026-10-06', 'summary': '前一天台股摘要'},
    ) is None


def test_no_tw_indices_does_not_claim_flat_market():
    from src.market_analyzer import MarketOverview

    report = tw_analyzer()._generate_template_review(MarketOverview(date='2026-10-07'), [])
    assert '行情資料不足，無法判斷走勢' in report
    assert '震荡整理' not in report


@pytest.mark.parametrize('dates', [
    {'trade_date': '2026-10-06'}, {'date': 'invalid'},
    {'date': '2026-10-07', 'trade_date': '2026-10-06'},
    {'date': 'invalid', 'trade_date': '2026-10-07'}, {},
])
def test_tw_invalid_or_conflicting_dates_cannot_use_same_query_bypass(dates):
    from src.services.daily_market_context import _record_matches_target_date

    payload = {'region': 'tw', 'summary': '台股摘要', **dates}
    service = DailyMarketContextService(db_manager=MagicMock())
    assert service._build_context_from_payload(
        region='tw', trade_date=date(2026, 10, 7), source='analysis_history', payload=payload,
    ) is None
    record = SimpleNamespace(query_id='same', created_at=datetime(2026, 10, 7), context_snapshot={})
    for strict in (False, True):
        assert not _record_matches_target_date(
            record=record, payload=payload, region='tw', target_date=date(2026, 10, 7),
            current_query_id='same', require_query_id_match=strict,
        )


@pytest.mark.parametrize('language', ['zh', 'en'])
def test_tw_partial_and_zero_index_changes_are_not_misrepresented(language):
    from src.market_analyzer import MarketIndex, MarketOverview

    analyzer = tw_analyzer(language)
    overview = MarketOverview(date='2026-10-07', indices=[
        MarketIndex(code='TWOII', name='櫃買指數', current=430.46, change=1, change_pct=0.2),
    ])
    report = analyzer._generate_template_review(overview, [])
    assert ('insufficient market data' if language == 'en' else '行情資料不足，無法判斷走勢') in report
    overview.indices.append(MarketIndex(code='TWII', name='加權指數', current=49806, change=0, change_pct=0))
    report = analyzer._generate_template_review(overview, [])
    assert ('unchanged' if language == 'en' else '平盤') in report

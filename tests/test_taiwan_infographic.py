"""Taiwan card acceptance at the public HTML entry point (offline)."""

import copy
import html
import re
from datetime import date

import pytest
from opencc import OpenCC

from src.share_image import build_share_image_html

TW = OpenCC("s2twp")
HOLD = "持仓者可续抱并设风险线；若跌破508.95元且无法收复，考虑减仓。"
ENTRY = "空仓者先观察开盘表现；若回踩523.80元附近缩量止稳，再考虑小仓分批介入。"
RISK = "新闻搜索覆盖有限，不代表已排除所有风险。"
STOCK = f"""## ⚪ NANYA TECHNOLOGY CORPORATION (2408.TW)

### 📌 核心结论
**⚪ 观望** | 震荡
> **一句话决策**: 均线多头且乖离安全，盘前先观察，不追价买进。
| 持仓情况 | 操作建议 |
|---------|---------|
| 空仓者 | {ENTRY} |
| 持仓者 | {HOLD} |

### 📈 当日行情
| 收盘 | 涨跌幅 | 成交量 | 成交额 |
|------|-------|--------|--------|
| 525.00 | -0.76% | 2994.79 万股 | N/A |

### 📊 数据透视
| 价格指标 | 当前价 |
|---------|------|
| 当前价 | 525.0 |
| MA5 | 523.8 |
| MA10 | 515.6 |
| MA20 | 508.95 |
| 支撑位 | 523.8 |
| 压力位 | 535.0 |
💡 *成交量约为前一日的0.85倍，尚无放量突破确认。*

### 🛡️ 盘中决策护栏
| 行动窗口 | 当前动作 | 下次检查 |
|---------|---------|---------|
| 盘前计划 | 等待确认 | 2026-10-07开盘后首小时，并于收盘后复核日线 |
**观察条件**:
- 详细观察条件仅完整报告显示。
**数据限制**:
- 行情数据标记为降级，盘前估算价不等于当日正式成交价。

### 🎯 作战计划
**仓位建议**: 详细部位仅完整报告显示。
- 建仓策略: 详细进场仅完整报告显示。
- 风控策略: 详细风控仅完整报告显示。
| 操作点位 | 当前价 |
|---------|------|
| 止损位 | 508.95元（有效跌破且无法收复时退出或减仓） |

### 信号归因分析
**最强看多信号**: MA5>MA10>MA20且现价仅高于MA5约0.23%
**最强看空信号**: 盘前行情降级、量比与筹码分布缺失，且无放量突破确认

### 重要信息速览
**风险警报**:
- {RISK}

### 三大法人动向（20261006 · TWSE-T86）
| 外资 | 投信 | 自营商 | 三大法人合计 |
|-----:|-----:|------:|------------:|
| +81.32 万股 | -50.60 万股 | +28.53 万股 | +59.24 万股 |
"""

MARKET = """# 大盘复盘
## 2026-10-08 臺股市場總覽
> 指數資料不齊，優先觀察承接，不推估缺漏數值。
### 二、指數結構
| 市場指數 | 收盤 | 漲跌幅 | 成交股數 | 成交金額（新臺幣億元） | 資料日期 |
|---|---:|---:|---:|---:|---|
| 櫃買指數 | 426.71 | -0.87% | 1,092,793,617 | 2,552.80 | 2026-10-08 |
### 成交量值比較
- 櫃買指數 / 前一交易日 (2026-10-07): 成交股數 -10.45%, 成交金額 -14.26%
### 法人、漲跌家數與類股
**TWSE / 上市 — 法人買賣超**
2026-10-08
| 法人 | 買進（億元） | 賣出（億元） | 買賣超（億元） |
|---|---:|---:|---:|
| 外資 | 2,819.34 | 3,577.86 | -758.52 |
| 投信 | 231.50 | 184.61 | +46.89 |
| 自營商合計 | 302.81 | 490.12 | -187.32 |
| 三大法人合計 | 3,353.64 | 4,252.59 | -898.95 |
**TWSE / 上市 — 漲跌家數**
2026-10-08
上漲／下跌／平盤: 425 / 540 / 109
**TWSE / 上市 — 類股價格指數排行**
2026-10-08
- 漲跌幅最高: 油電燃氣類指數 +3.04%、通訊網路類指數 +1.02%
- 漲跌幅最低: 綠能環保類指數 -2.57%、玻璃陶瓷類指數 -2.55%
### 四、明日交易計畫
- 關注方向：觀察櫃買止穩，無量突破不追。
- 觸發失效條件：若同步走弱且無法止穩，降低曝險並重新評估風險。
### 五、風險提示
- 未取得加權指數，不推估全市場方向。
- 類股排行為價格指數，不代表成交比重。
"""


def render(markdown="", payload=None):
    return build_share_image_html(markdown, structured_payload=payload, generated_on=date(2026, 10, 13))


def escaped(value):
    return html.escape(TW.convert(value).replace("計劃", "計畫"), quote=True)


def test_markdown_stock_keeps_action_meaning_and_selects_compact_blocks():
    card = render(STOCK)
    assert 'class="poster taiwan stock"' in card
    assert '<html lang="zh-TW">' in card
    assert escaped(HOLD) in card
    assert escaped(ENTRY) in card
    assert escaped(RISK) in card
    assert "反彈減倉" not in card
    assert "508.95 止損" not in card
    assert "詳細" not in card
    assert card.count('class="action"') == 3  # two conditions + next check
    assert "2026-10-07開盤後首小時，並於收盤後複核日線" in card
    assert 'class="price-axis"' in card
    assert '<b class="down">-50.60</b>' in card
    assert "資料日：20261006" in card
    assert "2994.79 萬股" in card
    assert 'class="metric down"' in card
    assert "均線多頭且乖離安全，盤前先觀察，不追價買進。" in card


@pytest.mark.parametrize("code", ["2330.TW", "6488.TWO", "00918.tw"])
def test_structured_stock_routes_without_markdown_and_never_truncates_selected_fields(code):
    hold = "持有但不可加碼；" + "等待有效支撐確認，" * 35 + "若收盤跌破100且隔日無法收復，才考慮減碼。"
    risk = "資料缺漏；" + "行情降級，" * 45 + "不能確認當日成交結果。"
    card = render("", {
        "code": code, "name": "長名稱" * 25,
        "dashboard": {
            "core_conclusion": {"one_sentence": "先觀察，不追價。",
                                "position_advice": {"no_position": ENTRY, "has_position": hold}},
            "intelligence": {"risk_alerts": [risk]},
            "battle_plan": {"position_strategy": {"suggested_position": "不可顯示部位詳細"}},
            "phase_decision": {"next_check_time": "下一交易日收盤後"},
        },
    })
    assert 'class="poster taiwan stock"' in card
    assert escaped(hold) in card and escaped(risk) in card
    assert "長名稱" * 25 in card
    assert "不可顯示部位詳細" not in card
    assert "…" not in card
    assert "交易日 未提供" in card  # generated_on is not a fabricated trade date


def test_stock_falls_back_to_full_entry_and_risk_control_only():
    entry = "若100支撐止穩且量價確認，才分批；未確認前不買。"
    risk = "若有效跌破95且无法收复，停止加仓并评估减仓。"
    card = render("", {"code": "2330.TW", "dashboard": {"battle_plan": {"position_strategy": {
        "entry_plan": entry, "risk_control": risk}}, "phase_decision": {"watch_conditions": ["省略清單全文"]}}})
    assert escaped(entry) in card and escaped(risk) in card
    assert card.count('class="action"') == 2
    assert "省略清單全文" not in card


@pytest.mark.parametrize("unit,expected", [(None, "單位未提供"), ("shares", "股"), ("lots", "張")])
def test_stock_volume_keeps_known_unit_and_does_not_guess(unit, expected):
    snapshot = {"volume": 12345}
    if unit:
        snapshot["volume_unit"] = unit
    card = render("", {"code": "2330.TW", "market_snapshot": snapshot})
    assert re.search(r"12345.*" + expected, card)
    if not unit:
        assert "12345 股" not in card and "12345 張" not in card


def test_stock_payload_overlays_markdown_without_rewriting_actions():
    card = render(STOCK, {
        "code": "2408.TW", "current_price": 520, "change_pct": 0,
        "dashboard": {"core_conclusion": {"position_advice": {"has_position": HOLD}}},
    })
    assert ">520.00</strong>" in card
    assert ">+0.00%</strong>" in card  # actual zero remains flat, not missing
    assert escaped(HOLD) in card and escaped(ENTRY) in card
    assert "反彈" not in card


def test_markdown_market_draws_actual_signed_flows_breadth_and_rankings():
    card = render(MARKET)
    assert 'class="poster taiwan market"' in card
    assert "交易日 2026-10-08" in card
    assert "TWII" in card and "TWOII" in card and "426.71" in card
    assert "2,552.80" in card and "-14.26%" in card
    assert '<b class="down">-758.52</b>' in card
    assert '<b class="up">+46.89</b>' in card
    assert "425 · 39.6%" in card
    assert "540 · 50.3%" in card
    assert "109 · 10.1%" in card
    assert "油電燃氣類指數" in card and "綠能環保類指數" in card
    assert "法人資料未提供" in card  # missing TPEx block is not zero
    assert "若同步走弱且無法止穩，降低曝險並重新評估風險。" in card
    assert "#d83e46" in card and "#00825c" in card


def market_payload():
    return {"region": "tw", "kind": "market_review", "date": "2026-10-08",
            "indices": [{"code": "TWII", "current": 49806.37, "change_pct": -0.03,
                         "amount": 986280000000, "amount_currency": "TWD", "trade_date": "2026-10-08",
                         "volume_comparison": {"previous_session": {"trade_date": "2026-10-07", "amount_change_pct": -12.5}}}],
            "taiwan_supplements": {"trade_date": "2026-10-08", "markets": {
                "twse": {
                    "institutions": {
                        "trade_date": "2026-10-08", "unit": "TWD",
                        "rows": [{"name": "外資", "net": -500000000}, {"name": "投信", "net": 0}, {"name": "自營商", "net": None}],
                    },
                    "breadth": {"trade_date": "2026-10-08", "unit": "stocks", "up": 0, "down": 3, "flat": 1},
                    "sectors": {"trade_date": "2026-10-08", "unit": "percent", "rows": [{"name": "甲", "change_pct": -1}, {"name": "乙", "change_pct": -3}]},
                },
            }}}


def test_structured_supplements_override_markdown_keep_negative_zero_and_missing():
    card = render(MARKET, market_payload())
    assert ">49,806.37</strong>" in card
    assert "9,862.80" in card and "-12.50%" in card
    assert '<b class="down">-5.00</b>' in card
    assert '<b class="flat">+0.00</b>' in card
    assert '<b class="flat">未提供</b>' in card
    assert "漲 0 · 0.0%" in card and "跌 3 · 75.0%" in card
    assert "-758.52" not in card
    assert ">甲</span><b class=\"down\">-1.00%" in card


@pytest.mark.parametrize("missing", [None, "N/A", "nan", float("inf"), "bad"])
def test_missing_numbers_do_not_turn_into_zero_or_nan(missing):
    payload = market_payload()
    payload["indices"][0]["current"] = missing
    payload["taiwan_supplements"]["markets"]["twse"]["breadth"]["up"] = missing
    card = render("", payload)
    assert '<strong>未提供</strong>' in card
    assert "漲跌平資料不足，不推估比例" in card
    assert "nan%" not in card and "inf%" not in card


def test_stale_supplements_do_not_overlay_today():
    payload = market_payload()
    for block in payload["taiwan_supplements"]["markets"]["twse"].values():
        block["trade_date"] = "2026-10-07"
    card = render(MARKET, payload)
    assert "-5.00" not in card and "-758.52" not in card
    assert "漲跌平資料不足" in card
    assert "類股排行未提供或日期不符" in card


def test_missing_structured_comparison_never_uses_conflicting_markdown():
    payload = market_payload()
    payload['indices'][0]['code'] = 'TWOII'
    payload['indices'][0]['volume_comparison']['previous_session']['amount_change_pct'] = None
    card = render(MARKET.replace('-14.26%', '+77.77%'), payload)
    assert '+77.77%' not in card and '-14.26%' not in card
    assert '前日比較未提供' in card


@pytest.mark.parametrize('kind, unit', [('institutions', 'TWD'), ('breadth', 'stocks'), ('sectors', 'percent')])
@pytest.mark.parametrize('invalid', [None, 'USD'])
def test_structured_blocks_require_explicit_matching_unit(kind, unit, invalid):
    payload = market_payload()
    block = payload['taiwan_supplements']['markets']['twse'][kind]
    block['unit'] = invalid
    card = render(MARKET, payload)
    if kind == 'institutions':
        assert '<b class="down">-5.00</b>' not in card
        assert '-758.52' not in card  # cannot replace invalid payload with Markdown
    elif kind == 'breadth':
        assert '漲跌平資料不足' in card
    else:
        assert '類股排行未提供或日期不符' in card


@pytest.mark.parametrize('kind', ['institutions', 'breadth', 'sectors'])
@pytest.mark.parametrize('invalid', [None, '2026-10-07', 'invalid'])
def test_structured_blocks_require_matching_trade_date(kind, invalid):
    payload = market_payload()
    payload['taiwan_supplements']['markets']['twse'][kind]['trade_date'] = invalid
    card = render(MARKET, payload)
    if kind == 'institutions':
        assert '<b class="down">-5.00</b>' not in card
    elif kind == 'breadth':
        assert '漲跌平資料不足' in card
    else:
        assert '類股排行未提供或日期不符' in card


def test_invalid_or_absent_structured_indices_do_not_use_markdown():
    payload = {'region': 'tw', 'date': '2026-10-08', 'indices': None}
    card = render(MARKET, payload)
    assert '426.71' not in card and '-14.26%' not in card
    payload['indices'] = [{'code': 'TWOII', 'current': 99999, 'trade_date': '2026-10-07'}]
    assert '99,999.00' not in render(MARKET, payload)


def test_unknown_index_currency_is_not_rendered_as_taiwan_dollars():
    payload = market_payload()
    payload['indices'][0]['amount_currency'] = 'USD'
    assert '9,862.80' not in render(MARKET, payload)


def test_markdown_market_rejects_undated_supplements():
    card = render(MARKET.replace('\n2026-10-08\n', '\n'))
    assert '-758.52' not in card and '425 · 39.6%' not in card
    assert '油電燃氣類指數' not in card


def test_markdown_index_date_mismatch_also_rejects_turnover_comparison():
    source = MARKET.replace('2026-10-08 |', '2026-10-07 |')
    card = render(source, {'region': 'tw', 'date': '2026-10-08'})
    assert '-14.26%' not in card


def test_market_attack_and_invalidation_conditions_are_preserved():
    entry = '進攻條件：加權止跌並站穩 49,000 點，同時櫃買跌勢收斂，才考慮分批布局。'
    invalidation = '失效條件：若再次跌破 49,000 點且櫃買跌幅擴大，應降低曝險。'
    source = '# 台股市場總覽\n### 明日交易計畫\n- **' + entry + '**\n- **' + invalidation + '**\n'
    card = render(source)
    assert escaped(entry) in card and escaped(invalidation) in card
    assert '觀察條件未提供' not in card


@pytest.mark.parametrize('code, english, chinese', [
    ('2330.TW', 'TAIWAN SEMICONDUCTOR MANUFACTUR', '台積電'),
    ('00918.TW', 'UOB ASSET MANAGEMENT (TAIWAN)CO', '大華優利高填息30'),
    ('009828.TW', 'CTBC INVESTMENTS CO LTD', '中信台日韓PCB'),
])
def test_chinese_security_name_is_primary_and_original_english_is_secondary(code, english, chinese):
    card = render(f'## {english} ({code})', {'code': code})
    assert f'<h1>{escaped(chinese)}<span class="english-name">({english})</span>' in card
    assert 'DSA ·' not in card


def test_supplied_chinese_name_is_used_without_guessing_unknown_symbols():
    card = render('## EXAMPLE (9999.TWO)', {'code': '9999.TWO', 'name_zh': '中文簡稱'})
    assert '<h1>中文簡稱<span class="english-name">(EXAMPLE)</span>' in card
    card = render('## EXAMPLE (9999.TWO)', {'code': '9999.TWO'})
    assert '<h1>EXAMPLE<span class="code">' in card


def test_html_escape_all_stock_fields_without_discarding_literal_conditions():
    value = '<script>alert("x")</script> & 若價格 < 100 且無法收復，才減碼。'
    card = render("", {"code": "2330.TW", "name": value, "dashboard": {
        "core_conclusion": {"one_sentence": value, "position_advice": {"has_position": value}},
        "intelligence": {"risk_alerts": [value]}}})
    assert escaped(value) in card
    assert "<script>" not in card and "&lt; 100" in card


def test_html_escape_market_names_and_prose():
    payload = market_payload()
    dangerous = '<img src=x onerror="alert(1)"> & 外資'
    payload["taiwan_supplements"]["markets"]["twse"]["institutions"]["rows"][0]["name"] = dangerous
    card = render(MARKET.replace("觀察承接", dangerous), payload)
    assert escaped(dangerous) in card
    assert '<img src=x' not in card


@pytest.mark.parametrize("source", ["[dsa-market-region]: # (tw)\n# 大盘复盘", "# 臺股市場總覽", "## 台股市場總覽"])
def test_taiwan_market_detection(source):
    assert 'class="poster taiwan market"' in render(source)


def test_non_taiwan_and_multi_stock_keep_legacy_routing():
    for payload in ({"code": "AAPL"}, {"code": "7203.T"}, {"kind": "market_review", "region": "us"}):
        assert 'class="poster taiwan' not in render("# Analysis Report", payload)
    assert 'class="poster dashboard"' in render("## 甲 (2330.TW)\n## 乙 (6488.TWO)")


def test_payload_is_not_mutated():
    payload = market_payload()
    before = copy.deepcopy(payload)
    render(MARKET, payload)
    assert before == payload


def test_stock_does_not_treat_financial_news_or_next_check_date_as_trade_date():
    source = "## 南亞科技 (2408.TW)\n\n報告期 2026-06-30\n新聞 2026-10-05\n下次檢查 2026-10-07"
    card = render(source)
    assert "交易日 未提供" in card
    assert "交易日 2026-06-30" not in card and "交易日 2026-10-05" not in card
    card = render(source, {"code": "2408.TW", "report_date": "2026-10-06"})
    assert "報告日期 2026-10-06" in card
    assert "交易日 2026-10-06" not in card
    financial_heading = "## 南亞科技 (2408.TW)\n\n## 財報期 2026-06-30\n\n## 新聞 2026-10-05"
    assert "交易日 未提供" in render(financial_heading)
    assert "交易日 未提供" in render("## 南亞科技 (2408.TW)", {"code": "2408.TW", "date": "2026-06-30"})


@pytest.mark.parametrize("date_payload", [
    {"trade_date": "2026-10-06"},
    {"market_snapshot": {"trade_date": "2026-10-06"}},
])
def test_explicit_trade_date_has_priority_over_report_and_financial_dates(date_payload):
    card = render("## 2026-10-07 南亞科技 (2408.TW)\n報告期 2026-06-30",
                  {"code": "2408.TW", "report_date": "2026-10-07", **date_payload})
    assert "交易日 2026-10-06" in card
    assert "交易日 2026-06-30" not in card


def test_stock_heading_date_is_report_date_and_explicit_quote_date_is_trade_date():
    source = "## 2026-10-07 南亞科技 (2408.TW)\n"
    assert "報告日期 2026-10-07" in render(source)
    quote = "\n### 當日行情\n| 收盤 | 資料日期 |\n|---|---|\n| 525 | 2026-10-06 |"
    assert "交易日 2026-10-06" in render(source + quote)


@pytest.mark.parametrize("invalid_date", [None, "", "2026-13-42", "N/A"])
def test_absent_or_invalid_dates_stay_unknown(invalid_date):
    card = render("## 南亞科技 (2408.TW)", {"code": "2408.TW", "trade_date": invalid_date})
    assert "交易日 未提供" in card

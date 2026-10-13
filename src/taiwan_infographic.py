"""Deterministic Taiwan infographics; keep supplied trading conditions verbatim.

Only select complete fields, rows and paragraphs. Never use the legacy compact
position/price helpers: they discard qualifiers or invent a different action.
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Mapping
from datetime import date

from opencc import OpenCC

from src.share_image import ShareImageBranding, _footer, _nested_mapping, _section
from src.data.stock_mapping import TAIWAN_SECURITY_NAME_MAP

_TW = OpenCC("s2twp")
_SYMBOL = re.compile(r"\b\d{4,6}\.TW(?:O)?\b", re.I)
_MISSING = {"", "n/a", "na", "none", "null", "nan", "--", "未提供", "資料缺漏"}


def _localize(text: str) -> str:
    return _TW.convert(text).replace("計劃", "計畫")


def taiwan_card_kind(markdown: str, payload: Mapping | None) -> str:
    payload = payload or {}
    code = str(payload.get("code") or "").strip()
    if code:
        return "stock" if _SYMBOL.fullmatch(code) else ""
    symbols = set()
    for heading in re.findall(r"^#{1,2}\s+(.+)$", markdown, re.M):
        symbols.update(_SYMBOL.findall(heading.upper()))
    if len(symbols) == 1:
        return "stock"
    if symbols:  # Aggregate reports must not turn into the first stock's card.
        return ""
    region = str(payload.get("region") or "").lower()
    if region:
        return "market" if region == "tw" else ""
    if re.search(r"\[dsa-market-region\]:\s*#\s*\(tw\)", markdown, re.I):
        return "market"
    if any(re.search(r"[台臺]股.*(?:(?:市場)?總覽|市場[覆復]盤|大盤[覆復]盤)", heading)
           for heading in re.findall(r"^#{1,2}\s+(.+)$", markdown, re.M)):
        return "market"
    return ""


def _text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"^>\s+", "", text)
    text = re.sub(r"^[\s*•✅⚠️❌📍💡⚪🆕💼]+", "", text).rstrip("*")
    text = re.sub(r"\s+", " ", text).strip()
    return "" if text.lower() in _MISSING else _localize(text)


def _e(value: object) -> str:
    return html.escape(_text(value), quote=True)


def _num(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(str(value).replace(",", "").strip().rstrip("%"))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _fmt(value: object, *, signed: bool = False, suffix: str = "") -> str:
    number = _num(value)
    if number is None:
        return "未提供"
    return (f"{number:+,.2f}" if signed else f"{number:,.2f}") + suffix


def _tone(value: object) -> str:
    number = _num(value)
    return "up" if number is not None and number > 0 else "down" if number is not None and number < 0 else "flat"


def _tables(markdown: str) -> list[tuple[list[str], list[list[str]]]]:
    # Raw cells avoid the legacy parser's 140-character truncation and HTML removal.
    tables = []
    for block in re.findall(r"(?:^\|[^\n]*\n?)+", markdown, re.M):
        rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
                for line in block.strip().splitlines()]
        if len(rows) >= 2 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]):
            tables.append(([_text(cell) for cell in rows[0]], rows[2:]))
    return tables


def _fields(markdown: str) -> dict:
    fields = {}
    for headers, rows in _tables(markdown):
        if len(rows) == 1:
            fields.update(zip(headers, rows[0]))
        for row in rows:
            if len(row) == 2:
                fields[_text(row[0])] = row[1]
    return fields


def _value(fields: Mapping, *labels: str) -> object:
    for key, value in fields.items():
        if any(label in key for label in labels):
            return value
    return None


def _prefer(*values: object) -> object:
    return next((value for value in values if _text(value)), None)


def _label(markdown: str, *labels: str) -> str:
    for line in markdown.splitlines():
        clean = _text(line).lstrip("- ")
        match = re.match(r"(?:[^\w<]*)(?:" + "|".join(map(re.escape, labels)) + r")\s*[:：]\s*(.*)", clean)
        if match:
            return match[1]
    return ""


def _items(markdown: str) -> list[str]:
    return [_text(line.lstrip("- ")) for line in markdown.splitlines()
            if line.strip() and not line.lstrip().startswith(("#", "|", "[dsa-"))]


def _after_label(markdown: str, label: str) -> list[str]:
    match = re.search(r"\*\*[^\n]*" + re.escape(label) + r"[^\n]*\*\*\s*[:：]?\s*\n(.*?)(?=\n\*\*|\n###|\Z)", markdown, re.S)
    return _items(match[1]) if match else []


def _list(values: list) -> str:
    return "<ul>" + "".join(f"<li>{_e(item)}</li>" for item in values if _text(item)) + "</ul>"


def _panel(title: str, body: str, cls: str = "") -> str:
    return f'<section class="panel {cls}"><h2>{_e(title)}</h2>{body}</section>'


def _metric(label: str, value: object, tone: str = "flat") -> str:
    return f'<div class="metric {tone}"><small>{_e(label)}</small><strong>{_e(value) or "未提供"}</strong></div>'


def _flow(rows: list[tuple[str, object]], unit: str) -> str:
    numbers = [_num(value) for _, value in rows]
    scale = max((abs(number) for number in numbers if number is not None), default=0)
    result = f'<p class="note">買賣超（{_e(unit)}）・左：賣超 ／ 右：買超</p>'
    for (name, value), number in zip(rows, numbers):
        tone = _tone(value)
        width = abs(number) / scale * 50 if number is not None and scale else 0
        left = 50 - width if number is not None and number < 0 else 50
        result += (f'<div class="flow-row"><span>{_e(name)}</span>'
                   f'<div class="signed-track"><i class="{tone}" style="left:{left:.3f}%;width:{width:.3f}%"></i></div>'
                   f'<b class="{tone}">{_fmt(value, signed=True)}</b></div>')
    return result


def _dated(block: Mapping, day: str) -> bool:
    return bool(_date_value(day) and _date_value(block.get("trade_date")) == day)


def _markdown_dated(block: str, day: str) -> bool:
    match = re.search(r"^(\d{4}-\d{2}-\d{2})(?:\s|/|$)", block, re.M)
    return bool(match and _date_value(day) and _date_value(match[1]) == day)


def _market_block(markdown: str, market: str, label: str) -> str:
    match = re.search(r"\*\*" + market + r"\s*/[^\n]*—[^\n]*" + label
                      + r"[^\n]*\*\*(.*?)(?=\n\*\*(?:TWSE|TPEx)|\n###|\Z)", markdown, re.S | re.I)
    return match[1] if match else ""


def _market(markdown: str, payload: Mapping, day: str) -> str:
    parsed = {}
    for headers, rows in _tables(markdown):
        if not any("市場指數" in header or "Market index" in header for header in headers):
            continue
        for row in rows:
            fields = dict(zip(headers, row))
            name = row[0]
            code = "TWOII" if "櫃買" in name else "TWII" if "加權" in name else ""
            if code:
                amount = _num(_value(fields, "成交金額", "Turnover"))
                parsed[code] = {"current": _value(fields, "收盤", "Close"),
                                "change_pct": _value(fields, "漲跌幅", "Change %"),
                                "amount": amount * 1e8 if amount is not None else None,
                                "trade_date": _value(fields, "資料日期", "Trade date")}
    raw_indices = payload.get("indices")
    indices = {str(row.get("code")): row for row in raw_indices if isinstance(row, Mapping)} if isinstance(raw_indices, list) else {}
    structured_indices = "indices" in payload
    index_cards = []
    for code, name in (("TWII", "加權指數"), ("TWOII", "櫃買指數")):
        idx = indices.get(code, {}) if structured_indices else parsed.get(code, {})
        if not _dated(idx, day):
            idx = {}
        change = idx.get("change_pct")
        amount = _num(idx.get("amount")) if not structured_indices or idx.get("amount_currency") == "TWD" else None
        previous = _nested_mapping(idx, "volume_comparison", "previous_session")
        comparison = _num(previous.get("amount_change_pct"))
        comparison_date = previous.get("trade_date")
        if comparison is None and not structured_indices and _dated(idx, day):
            match = re.search(r"- [^\n]*" + ("櫃買" if code == "TWOII" else "加權")
                              + r"[^\n]*/ 前一交易日 \(([^)]+)\):[^\n]*成交金額 ([+-]?[\d.]+)%", markdown)
            if match:
                comparison_date, comparison = match[1], _num(match[2])
        if not (_date_value(comparison_date) and _date_value(day) and comparison_date < day):
            comparison = None
        compare = (f"較前日 {_fmt(comparison, signed=True, suffix='%')}（{comparison_date or '比較日期未提供'}）"
                   if comparison is not None else "前日比較未提供，不判斷放量／縮量")
        index_cards.append(
            f'<section class="index"><small>{name} · {code}</small>'
            f'<strong>{_fmt(idx.get("current"))}</strong>'
            f'<b class="{_tone(change)}">{_fmt(change, signed=True, suffix="%")}</b>'
            f'<p>成交金額 {_fmt(amount / 1e8 if amount is not None else None)} 億元</p>'
            f'<p class="note">{_e(compare)}</p><small>資料日：{_e(idx.get("trade_date")) or "未提供"}</small></section>'
        )
    result = '<div class="grid">' + "".join(index_cards) + "</div>"
    markets = _nested_mapping(payload, "taiwan_supplements", "markets")
    structured_supplements = "taiwan_supplements" in payload
    for key, official, name in (("twse", "TWSE", "上市"), ("tpex", "TPEx", "上櫃")):
        data = _nested_mapping(markets, key)
        institutions = _nested_mapping(data, "institutions")
        inst_md = _market_block(markdown, official, "法人買賣超")
        flow = []
        if structured_supplements:
            if _dated(institutions, day) and institutions.get("unit") == "TWD":
                flow = [(_text(row.get("name")), _num(row.get("net")) / 1e8 if _num(row.get("net")) is not None else None)
                        for row in institutions.get("rows", []) if isinstance(row, Mapping)]
        elif _markdown_dated(inst_md, day):
            for headers, rows in _tables(inst_md):
                if any("買賣超" in header and "億元" in header for header in headers):
                    flow = [(row[0], row[-1]) for row in rows if len(row) == len(headers)]
        flow_html = _flow(flow, "新臺幣億元") if flow else '<p class="missing">法人資料未提供或日期不符</p>'
        universe = institutions.get("universe") or _label(inst_md, "統計範圍")
        flow_html += f'<p class="note">{_e(universe)}</p>' if universe else ""
        breadth = _nested_mapping(data, "breadth")
        breadth_md = _market_block(markdown, official, "漲跌家數")
        counts = [breadth.get(kind) for kind in ("up", "down", "flat")] if structured_supplements else []
        breadth_dated = _dated(breadth, day) and breadth.get("unit") == "stocks"
        if not structured_supplements and _markdown_dated(breadth_md, day):
            match = re.search(r"上漲／下跌／平盤:\s*([\d,]+)\s*/\s*([\d,]+)\s*/\s*([\d,]+)", breadth_md)
            counts = list(match.groups()) if match else []
            breadth_dated = True
        values = [_num(value) for value in counts]
        valid = len(values) == 3 and all(value is not None and value >= 0 and value.is_integer() for value in values)
        if valid and breadth_dated and sum(values) > 0:
            total = sum(values)
            breadth_html = '<div class="breadth">' + "".join(
                f'<i class="{tone}" style="width:{value / total * 100:.4f}%"></i>'
                for value, tone in zip(values, ("up", "down", "flat"))) + "</div>"
            breadth_html += '<p class="legend">' + " ／ ".join(
                f'<span class="{tone}">{label} {value:,.0f} · {value / total:.1%}</span>'
                for value, tone, label in zip(values, ("up", "down", "flat"), ("漲", "跌", "平"))) + "</p>"
            breadth_html += '<p class="note">比例分母為漲＋跌＋平，不含未成交／無比較價格。</p>'
        else:
            breadth_html = '<p class="missing">漲跌平資料不足，不推估比例</p>'
        result += '<div class="grid">' + _panel(f"{name}三大法人", flow_html) + _panel(f"{name}漲跌家數", breadth_html) + "</div>"
        sectors = _nested_mapping(data, "sectors")
        sector_md = _market_block(markdown, official, "類股價格指數排行")
        ranking = []
        if structured_supplements and _dated(sectors, day) and sectors.get("unit") == "percent":
            ranking = [(row.get("name"), _num(row.get("change_pct")))
                       for row in sectors.get("rows", []) if isinstance(row, Mapping) and _num(row.get("change_pct")) is not None]
        elif not structured_supplements and _markdown_dated(sector_md, day):
            ranking = [(match[1].strip(), _num(match[2])) for match in re.finditer(
                r"(?:最高:|最低:|、)\s*([^、\n]+?)\s+([+-]?[\d.]+)%", sector_md)]
        ranked = sorted(ranking, key=lambda row: row[1], reverse=True)
        if ranked:
            parts = []
            for label, entries in (("相對強勢", ranked[:2]), ("相對弱勢", ranked[-2:][::-1])):
                parts.append(f'<div><h3>{label}</h3>' + "".join(
                    f'<p class="sector"><span>{_e(title)}</span><b class="{_tone(change)}">{_fmt(change, signed=True, suffix="%")}</b></p>'
                    for title, change in entries) + "</div>")
            result += _panel(f"{name}類股", '<div class="grid">' + "".join(parts) + '</div><p class="note">依官方類股價格指數；相對強勢不代表上漲。</p>')
        else:
            result += _panel(f"{name}類股", '<p class="missing">類股排行未提供或日期不符</p>')
    plan = _section(markdown, "明日交易計畫", "下一交易日", "策略框架", "Trading Plan")
    watch = [line for line in _items(plan) if any(term in line for term in ("關注方向", "觸發失效", "觀察", "進攻條件", "失效條件", "Guidance"))]
    result += _panel("下一次觀察", _list(watch[:2]) if watch else '<p class="missing">觀察條件未提供</p>')
    risks = _items(_section(markdown, "風險提示", "Risk"))
    result += _panel("風險與資料限制", _list(risks[:2]) if risks else '<p class="missing">原報告未提供風險段落；缺漏數據不推估。</p>', "risk")
    return result


def _stock(markdown: str, payload: Mapping) -> str:
    dashboard = _nested_mapping(payload, "dashboard")
    core = _nested_mapping(dashboard, "core_conclusion")
    view = _nested_mapping(dashboard, "data_perspective")
    price = _nested_mapping(view, "price_position")
    volume = _nested_mapping(view, "volume_analysis")
    snapshot = _nested_mapping(payload, "market_snapshot")
    quote = _fields(_section(markdown, "當日行情", "市場快照", "Market Snapshot"))
    technical = _section(markdown, "資料透視", "數據透視", "Data View")
    tech_fields = _fields(technical)
    current = _prefer(payload.get("current_price"), price.get("current_price"), snapshot.get("price"), snapshot.get("close"), _value(quote, "當前價", "目前價", "收盤"))
    change = _prefer(payload.get("change_pct"), snapshot.get("pct_chg"), _value(quote, "漲跌幅"))
    traded = _prefer(snapshot.get("volume"), _value(quote, "成交量"))
    if _num(snapshot.get("volume")) is not None:
        unit = {"shares": "股", "lots": "張"}.get(snapshot.get("volume_unit"), _text(snapshot.get("volume_unit")))
        traded = f'{_text(snapshot["volume"])} {unit or "（單位未提供）"}'
    result = '<div class="metrics">' + _metric("現價／收盤", _fmt(current)) + _metric("漲跌幅", _fmt(change, signed=True, suffix="%"), _tone(change)) + _metric("成交量", traded) + "</div>"
    volume_evidence = next((line for line in _items(technical) if "前一日" in line or "前一交易日" in line), "")
    volume_evidence = _prefer(volume.get("volume_meaning"), payload.get("volume_analysis"), volume_evidence)
    if volume_evidence and len(_text(volume_evidence)) > 110:
        comparison = re.search(r"成交量約?為前一(?:日|交易日)的[\d.]+倍", _text(volume_evidence))
        volume_evidence = comparison[0] if comparison else "成交變化詳見完整報告"
    result += f'<p class="volume-note">{_e(volume_evidence) or "成交變化未提供；量比不視為前日成交量變化。"}</p>'
    source = _prefer(snapshot.get("source"), _value(quote, "行情來源"))
    if source:
        result += f'<p class="note">行情來源：{_e(source)}</p>'
    levels = [("支撐", _prefer(price.get("support_level"), _value(tech_fields, "支撐位"))),
              ("現價", current),
              ("壓力", _prefer(price.get("resistance_level"), _value(tech_fields, "壓力位")))]
    numeric = [_num(value) for _, value in levels]
    if all(value is not None and value > 0 for value in numeric) and min(numeric) < max(numeric):
        positions_on_axis = [(value - min(numeric)) / (max(numeric) - min(numeric)) * 80 + 10 for value in numeric]
        axis = '<div class="price-axis">' + "".join(
            f'<i class="{cls}" style="left:{position:.3f}%" title="{_e(label)} {_fmt(value)}"></i>'
            for cls, (label, value), position in zip(("support", "current", "resistance"), levels, positions_on_axis)) + "</div>"
    else:
        axis = '<p class="missing">價位資料不足或無可比較區間，不推估軸上位置。</p>'
    result += _panel("支撐／現價／壓力", axis + '<div class="metrics">' + "".join(_metric(label, _fmt(value)) for label, value in levels) + "</div>")
    attribution = _nested_mapping(dashboard, "signal_attribution")
    ma_values = " ／ ".join(
        f'{key} {_fmt(tech_fields[key])}' for key in ("MA5", "MA10", "MA20")
        if _num(tech_fields.get(key)) is not None
    )
    candidates = [
        (attribution.get("strongest_bullish_signal"), _label(markdown, "最強看多訊號", "最強看多信號"),
         _nested_mapping(view, "trend_status").get("ma_alignment"), ma_values),
        (attribution.get("strongest_bearish_signal"), _label(markdown, "最強看空訊號", "最強看空信號"),
         volume.get("volume_status"), volume_evidence),
    ]
    # Select a whole short source field; never shorten away its qualification.
    reasons = [next((_text(value) for value in choices if _text(value) and len(_text(value)) <= 110), "主要依據未提供短欄位")
               for choices in candidates]
    result += _panel("兩個主要依據", _list(reasons) if any(reasons) else '<p class="missing">主要依據未提供</p>')
    inst_section = _section(markdown, "三大法人動向", "Institutional")
    flow = []
    for headers, rows in _tables(inst_section):
        if rows and any("外資" in header for header in headers):
            for header, cell in zip(headers, rows[0]):
                match = re.fullmatch(r"([+-]?[\d,.]+)\s*(萬股|億股|股)?", _text(cell))
                if match:
                    value = _num(match[1])
                    multiplier = {"萬股": 1, "億股": 10000, "股": 0.0001, None: 0.0001}[match[2]]
                    flow.append((header, value * multiplier if value is not None else None))
                else:
                    flow.append((header, None))
    if flow:
        date_match = re.search(r"三大法人動向[^\n]*", markdown)
        heading = _text(date_match[0]) if date_match else "三大法人"
        inst_dates = re.findall(r"\d{8}|\d{4}-\d{2}-\d{2}", heading)
        result += _panel("三大法人", f'<p class="note">資料日：{_e(inst_dates[0]) if inst_dates else "未提供"}</p>' + _flow(flow, "萬股"))
    else:
        result += _panel("三大法人", '<p class="missing">法人資料未提供</p>')
    positions = _nested_mapping(core, "position_advice")
    core_md = _section(markdown, "核心結論", "Core Conclusion")
    position_fields = _fields(core_md)
    battle = _nested_mapping(dashboard, "battle_plan")
    strategy = _nested_mapping(battle, "position_strategy")
    battle_md = _section(markdown, "作戰計畫", "Battle Plan")
    actions = []
    primary_actions = [
        ("空手", _prefer(positions.get("no_position"), _value(position_fields, "空倉者"))),
        ("持有", _prefer(positions.get("has_position"), _value(position_fields, "持倉者"))),
    ]
    fallback_actions = [
        ("進場", _prefer(strategy.get("entry_plan"), _label(battle_md, "建倉策略"))),
        ("風控", _prefer(strategy.get("risk_control"), _label(battle_md, "風控策略"))),
    ]
    for primary, fallback in zip(primary_actions, fallback_actions):
        label, value = primary if _text(primary[1]) else fallback
        if _text(value):
            actions.append(f'<div class="action"><b>{label}</b><p>{_e(value)}</p></div>')
    phase = _nested_mapping(dashboard, "phase_decision")
    guard = _section(markdown, "盤中決策護欄", "Phase Decision")
    guard_fields = _fields(guard)
    next_check = _prefer(phase.get("next_check_time"), _value(guard_fields, "下次檢查"))
    if _text(next_check):
        actions.append(f'<div class="action"><b>下次檢查</b><p>{_e(next_check)}</p></div>')
    result += _panel("關鍵行動條件", "".join(actions) if actions else '<p class="missing">原報告未提供行動條件</p>')
    limitations = phase.get("data_limitations") or _after_label(guard, "資料限制") or _after_label(guard, "數據限制")
    risks = (_nested_mapping(dashboard, "intelligence").get("risk_alerts")
             or _after_label(markdown, "風險警報")
             or ([payload["risk_warning"]] if payload.get("risk_warning") else []))
    selected = (list(limitations[:1]) if isinstance(limitations, list) else []) + (list(risks[:1]) if isinstance(risks, list) else [])
    if len(selected) < 2 and isinstance(limitations, list):
        selected.extend(limitations[1:2])
    result += _panel("風險與資料限制", _list(selected[:2]) if selected else '<p class="missing">原報告未提供風險／資料限制；缺漏數據不推估。</p>', "risk")
    return result


_CSS = """*{box-sizing:border-box}html,body{margin:0;width:1080px;background:#edf2f8}
body{font:22px/1.55 "Noto Sans CJK TC","Microsoft JhengHei","PingFang TC",sans-serif;color:#14243b}
.poster{padding:36px;background:linear-gradient(150deg,#f7faff,#edf3fb)}
header{display:flex;justify-content:space-between;align-items:center;color:#496481;font-size:20px;border-bottom:2px solid #c9d8e9;padding-bottom:16px}
.brand{font-size:28px;font-weight:800;color:#205789}h1{font-size:46px;line-height:1.2;overflow-wrap:anywhere;margin:22px 0 10px;letter-spacing:-.5px}
.english-name{display:block;font-size:20px;font-weight:400;line-height:1.5;color:#64748b;letter-spacing:0;margin-top:8px}
.code{display:block;color:#346596;font-size:26px;letter-spacing:1px;margin-top:8px}.conclusion{font-size:27px;font-weight:700;border-left:6px solid #366caa;padding:16px 20px;background:#e0ebf8;border-radius:12px;margin:16px 0 22px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:16px}.grid>.panel{margin:0}
.panel,.index{padding:20px 24px;border:1px solid #cbd9e9;border-radius:18px;background:#fff;margin-bottom:16px;min-width:0}
h2{font-size:25px;margin:0 0 14px;color:#244e79}h3{font-size:20px;color:#526986;margin:4px 0}p{margin:6px 0;overflow-wrap:anywhere}ul{padding-left:26px;margin:8px 0}li{margin:8px 0;overflow-wrap:anywhere}
.index strong{display:block;font-size:56px;line-height:1.2;letter-spacing:-1px;margin:10px 0}.index>b{font-size:30px}.index p{font-size:21px}.index small{color:#647c97;font-size:19px}
.note{font-size:17px;color:#667991}.missing{font-size:20px;color:#817148}.up{color:#d83e46}.down{color:#00825c}.flat{color:#788797}
.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.metric{padding:12px;border:1px solid #d4e1ef;border-radius:12px;background:#f8fbff;text-align:center;min-width:0}.metric small{display:block;font-size:19px}.metric strong{font-size:30px;display:block;overflow-wrap:anywhere}
.volume-note{margin:14px 4px;font-size:20px}.flow-row{display:grid;grid-template-columns:130px minmax(0,1fr) 116px;gap:8px;align-items:center;margin:14px 0;font-size:18px}.flow-row b{text-align:right}.signed-track{height:22px;position:relative;background:#edf2f7;border-radius:4px}.signed-track:after{content:"";position:absolute;left:50%;height:30px;top:-4px;border-left:1px solid #8c9daf}.signed-track i{position:absolute;height:22px;border-radius:3px}.signed-track .up,.breadth .up{background:#d83e46}.signed-track .down,.breadth .down{background:#00825c}.breadth .flat{background:#99a6b6}
.breadth{display:flex;height:40px;border-radius:10px;overflow:hidden;margin:30px 0 14px}.legend{font-size:18px}.sector{display:flex;gap:12px;justify-content:space-between;font-size:21px}.sector span{overflow-wrap:anywhere}.sector b{white-space:nowrap}.price-axis{height:48px;position:relative;margin:10px 0 12px}.price-axis:before{content:"";position:absolute;left:10%;right:10%;height:4px;top:24px;background:#aac0d9}.price-axis i{position:absolute;width:16px;height:16px;border-radius:50%;top:18px;transform:translateX(-50%);background:#346ca5}.price-axis .current{height:24px;width:24px;top:14px;background:#153959;border:3px solid #fff;box-shadow:0 0 0 2px #153959}
.action{display:grid;grid-template-columns:104px minmax(0,1fr);gap:14px;padding:9px 0;border-bottom:1px solid #e6edf5}.action b{font-size:19px;color:#3e6590}.action p{margin:0;font-size:20px}.risk{background:#fff9ed;border-color:#e5d5b5}.risk h2{color:#80602a}.risk li{font-size:20px}
.poster-footer{border-top:1px solid #cbd9e9;margin-top:24px;padding-top:14px;font-size:15px;color:#64748b}.footer-title,.repo-line,.qr-card{display:none}.disclaimer{margin-top:8px}.footer-brand>small{font-size:15px}
"""


def _date_value(value: object) -> str:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _card_date(markdown: str, payload: Mapping, kind: str) -> tuple[str, str]:
    headings = []
    for level, title in re.findall(r"^(#{1,2})\s+(.+)$", markdown, re.M):
        if kind == "stock":
            if _SYMBOL.search(title) or (level == "#" and re.search(r"儀表|報告|Report|Dashboard", title, re.I)):
                headings.append(title)
        elif re.search(r"[台臺]股|大盤|市場|Market", title, re.I):
            headings.append(title)
    heading_dates = re.findall(r"\d{4}-\d{2}-\d{2}", " ".join(headings))
    heading_day = _date_value(heading_dates[0]) if heading_dates else ""
    if kind == "market":
        return "交易日", _date_value(payload.get("date")) or _date_value(payload.get("trade_date")) or heading_day
    quote = _fields(_section(markdown, "當日行情", "市場快照", "Market Snapshot"))
    trade_day = next((day for value in (
        payload.get("trade_date"), _nested_mapping(payload, "market_snapshot").get("trade_date"),
        _value(quote, "交易日", "行情資料日期", "資料日期"),
    ) if (day := _date_value(value))), "")
    if trade_day:
        return "交易日", trade_day
    report_day = _date_value(payload.get("report_date")) or heading_day
    return ("報告日期", report_day) if report_day else ("交易日", "")


def build_taiwan_infographic(markdown: str, payload: Mapping, kind: str, branding: ShareImageBranding) -> str:
    markdown = _localize(markdown or str(payload.get("markdown_report") or ""))
    if not markdown and isinstance(payload.get("sections"), list):
        markdown = _localize("\n\n".join(
            f'### {section.get("title", "")}\n{section.get("markdown", "")}'
            for section in payload["sections"] if isinstance(section, Mapping)))
    headings = re.findall(r"^#{1,2}\s+(.+)$", markdown, re.M)
    date_label, day = _card_date(markdown, payload, kind)
    if kind == "stock":
        heading = next((title for title in headings if _SYMBOL.search(title)), "")
        match = _SYMBOL.search(heading)
        code = str(payload.get("code") or (match[0] if match else ""))
        name = _text(payload.get("name"))
        if not name and match:
            name = _text(heading[:match.start()].rstrip(" (（"))
        core = _nested_mapping(payload, "dashboard", "core_conclusion")
        core_md = _section(markdown, "核心結論", "Core Conclusion")
        conclusion = _prefer(core.get("one_sentence"), _label(core_md, "一句話決策", "One-line Decision"), payload.get("analysis_summary"))
        action = _prefer(payload.get("action_label"), payload.get("operation_advice"), next(iter(_items(core_md)), ""))
        chinese_name = _text(payload.get("name_zh")) or (name if re.search(r"[\u4e00-\u9fff]", name) else TAIWAN_SECURITY_NAME_MAP.get(code.upper(), ""))
        english_name = _text(payload.get("english_name")) or (name if name and not re.search(r"[\u4e00-\u9fff]", name) else "")
        title = chinese_name or name or "台股個股"
        hero = (f'<span class="english-name">({_e(english_name)})</span>' if chinese_name and english_name else "")
        hero += f'<span class="code">{_e(code)}</span>'
        summary = f'{_e(action)}<p>{_e(conclusion) or "原分析結論未提供"}</p>'
        content = _stock(markdown, payload)
    else:
        title, hero = "台股市場總覽", ""
        summary = _e(next((line[1:].strip() for line in markdown.splitlines() if line.startswith("> ") and "預覽" not in line), "")) or "原報告一句結論未提供"
        content = _market(markdown, payload, day)
    footer = _TW.convert(_footer(branding, "", "zh"))
    return (f'<!DOCTYPE html><html lang="zh-TW"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=1080, initial-scale=1"><title>{_e(title)}</title><style>{_CSS}</style></head>'
            f'<body><main class="poster taiwan {kind}"><header><span class="brand">台股資訊圖卡</span>'
            f'<span>{date_label} {_e(day) or "未提供"}</span></header><h1>{_e(title)}{hero}</h1>'
            f'<div class="conclusion">{summary}</div>{content}{footer}</main></body></html>')

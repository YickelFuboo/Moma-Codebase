from typing import Literal, TypedDict

MarketCode = Literal["CN_A", "HK"]
BarFreq = Literal["1d", "1w", "1m", "1m_intraday", "5m_intraday"]
AdjustType = Literal["qfq", "hfq", "none"]

INDEX_ALIASES: dict[str, str] = {
    "000985": "中证全指",
    "000985.SH": "中证全指",
    "csi_all": "中证全指",
    "000300": "沪深300",
    "000300.SH": "沪深300",
    "hs300": "沪深300",
    "000688": "科创50",
    "000688.SH": "科创50",
    "000905": "中证500",
    "399006": "创业板指",
    "HSI": "恒生指数",
    "HSI.HK": "恒生指数",
    "hsi": "恒生指数",
    "SPX": "标普500",
    "SP500": "标普500",
    "NDX": "纳斯达克100",
    "NASDAQ100": "纳斯达克100",
    "DAX": "德国DAX",
    "N225": "日经225",
    "NI225": "日经225",
    "VIX": "VIX",
}

GLOBAL_INDEX_EM_NAMES: dict[str, str] = {
    "SPX": "标普500",
    "SP500": "标普500",
    "NDX": "纳斯达克100",
    "NASDAQ100": "纳斯达克100",
    "DAX": "德国DAX",
    "N225": "日经225",
    "NI225": "日经225",
    "VIX": "VIX",
}

INDEX_TS_CODES: dict[str, str] = {
    "000985": "000985.CSI",
    "000985.SH": "000985.CSI",
    "csi_all": "000985.CSI",
    "000300": "000300.SH",
    "000300.SH": "000300.SH",
    "hs300": "000300.SH",
    "000688": "000688.SH",
    "000688.SH": "000688.SH",
    "000905": "000905.SH",
    "399006": "399006.SZ",
}

INDEX_WIND_CODES: dict[str, str] = {
    "000985": "000985.CSI",
    "000985.SH": "000985.CSI",
    "csi_all": "000985.CSI",
    "000300": "000300.SH",
    "000300.SH": "000300.SH",
    "hs300": "000300.SH",
    "000688": "000688.SH",
    "000688.SH": "000688.SH",
    "000905": "000905.SH",
    "399006": "399006.SZ",
    "HSI": "HSI.HI",
    "HSI.HK": "HSI.HI",
    "hsi": "HSI.HI",
}

WIND_CN_10Y_EDB = "M1000166"

WIND_MACRO_EDB: dict[str, str] = {
    "cn_10y": "M1000166",
    "cn_1y": "M1005931",
    "us_10y": "G0000891",
    "dr007": "M0075991",
    "shibor_1w": "M0017139",
    "shibor_1m": "M0017140",
}

CHOICE_MACRO_EDB: dict[str, str] = {
    "cn_10y": "S0059749",
    "us_10y": "G0000891",
}
def resolve_index(index: str) -> str:
    text = (index or "").strip()
    if not text:
        return text
    if text in INDEX_ALIASES or text in INDEX_TS_CODES or text in INDEX_WIND_CODES:
        return text
    if text in GLOBAL_INDEX_EM_NAMES:
        return text
    for key, name in INDEX_ALIASES.items():
        if name == text:
            return key
    for key, name in GLOBAL_INDEX_EM_NAMES.items():
        if name == text:
            return key
    lower = text.lower()
    for key in INDEX_ALIASES:
        if key.lower() == lower:
            return key
    for key in GLOBAL_INDEX_EM_NAMES:
        if key.lower() == lower:
            return key
    return text


def is_global_index(index: str) -> bool:
    resolved = resolve_index(index)
    return resolved in GLOBAL_INDEX_EM_NAMES or resolve_index(resolved) in GLOBAL_INDEX_EM_NAMES


def global_index_em_name(index: str) -> str:
    resolved = resolve_index(index)
    if resolved in GLOBAL_INDEX_EM_NAMES:
        return GLOBAL_INDEX_EM_NAMES[resolved]
    for key, name in GLOBAL_INDEX_EM_NAMES.items():
        if name == resolved:
            return name
    return resolved


def is_hsi_index(index: str) -> bool:
    resolved = resolve_index(index).upper()
    alias = INDEX_ALIASES.get(resolved, "")
    return resolved in {"HSI", "HSI.HK", "HSI.HI"} or alias == "恒生指数" or index.strip() == "恒生指数"


class DataMeta(TypedDict, total=False):
    source: str
    provider: str
    as_of_date: str
    market: str
    symbol: str
    adjust: str
    delayed: bool
    note: str

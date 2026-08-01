# -*- coding: utf-8 -*-
"""
坐标系转换工具 · Streamlit 版
=================================
WGS-84 ⇄ GCJ-02 ⇄ BD-09，公开标准算法，纯离线（不调用任何联网 API）。
可直接部署到 Streamlit Community Cloud（https://share.streamlit.io）。

依赖仅 streamlit + pandas；海陆/境内判断用内置简化边界做纯 Python 射线法，
无需 geopandas / GDAL，部署轻量可靠。
"""
import io
import json
import os

import pandas as pd
import streamlit as st

import coord_transform as C

# --------------------------------------------------------------------------
# 基本配置
# --------------------------------------------------------------------------
st.set_page_config(page_title="坐标系转换工具 · WGS-84/GCJ-02/BD-09",
                   page_icon="🧭", layout="wide")

HERE = os.path.dirname(os.path.abspath(__file__))
BOUNDARY_PATH = os.path.join(HERE, "china_boundary_gcj02.json")

SYS_LABEL = {"wgs84": "WGS-84", "gcj02": "GCJ-02", "bd09": "BD-09"}
SYS_DESC = {"wgs84": "WGS-84（GPS / 真实坐标）",
            "gcj02": "GCJ-02（高德 / 腾讯 / 火星）",
            "bd09": "BD-09（百度）"}

# 列名 / 坐标系 识别关键词（与 batch_convert.py 保持一致）
LON_KEYS = ("lon", "lng", "longitude", "经度", "经", "x")
LAT_KEYS = ("lat", "latitude", "纬度", "纬", "y")
SYS_KEYS = {"wgs84": ("wgs84", "wgs", "gps"),
            "gcj02": ("gcj02", "gcj", "gaode", "高德", "火星", "amap"),
            "bd09": ("bd09", "bd-09", "baidu", "百度")}

SAMPLE_CSV = """name,lon_wgs84,lat_wgs84
天安门,116.397128,39.908722
上海外滩,121.490317,31.236305
广州塔,113.32452,23.106414
成都天府广场,104.065751,30.657457
西安钟楼,108.945227,34.263161
深圳市民中心,114.058921,22.546248
杭州西湖,120.148429,30.236764
武汉黄鹤楼,114.302976,30.543141
南京新街口,118.789423,32.041546
重庆解放碑,106.577023,29.559416
错点_经纬度写反,39.908722,116.397128
错点_落在巴黎,2.352222,48.856614
错点_落在东海,123.5,30.0
错点_零值,0.0,0.0"""


# --------------------------------------------------------------------------
# 海陆 / 境内判断（射线法，边界数值为 GCJ-02）
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_boundary():
    try:
        with open(BOUNDARY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _in_ring(lng, lat, ring):
    inside, n, j = False, len(ring), len(ring) - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def off_land(lng_wgs, lat_wgs, rings):
    """WGS-84 点是否落在中国陆地之外；rings 为空则返回 None（未知）。"""
    if not rings:
        return None
    gl, ga = C.wgs84_to_gcj02(lng_wgs, lat_wgs)
    return not any(_in_ring(gl, ga, ring) for ring in rings)


def validate_full(lng, lat, src, rings):
    """数值校验 + （源为 WGS-84 时）海陆提示，结论与 batch_convert.py 一致。"""
    v = C.validate_point(lng, lat)
    status = v["status"]
    issues = [i for i in v["issues"] if i != "正常"]
    try:
        nl, na = float(lng), float(lat)
    except (TypeError, ValueError):
        return status, (issues or ["正常"]), v["suggestion"]
    if (src == "wgs84" and status != "error"
            and -180 <= nl <= 180 and -90 <= na <= 90
            and not C.out_of_china(nl, na)
            and not (abs(nl) < 1e-9 and abs(na) < 1e-9)
            and off_land(nl, na, rings) is True):
        issues.append("落在中国陆地边界之外（疑似海上或境外，请核对）")
        if status == "ok":
            status = "warning"
    return status, (issues or ["正常"]), v["suggestion"]


# --------------------------------------------------------------------------
# CSV / 列识别
# --------------------------------------------------------------------------
def read_csv_bytes(b):
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return pd.read_csv(io.BytesIO(b), encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(io.BytesIO(b))


def detect_col(cols, keys):
    low = [str(c).lower() for c in cols]
    for i, c in enumerate(cols):
        if any(k in low[i] for k in keys):
            return c
    return None


def detect_system(name):
    if name is None:
        return None
    low = str(name).lower()
    for s, keys in SYS_KEYS.items():
        if any(k in low for k in keys):
            return s
    return None


def fmt(x):
    return ("%.7f" % float(x)).rstrip("0").rstrip(".")


# --------------------------------------------------------------------------
# 批量处理
# --------------------------------------------------------------------------
def process(df, name_col, lon_col, lat_col, src, rings):
    """返回 (下载用 DataFrame, 展示用 DataFrame, 计数字典)。"""
    dl_rows, show_rows = [], []
    n_ok = n_warn = n_err = 0
    for _, r in df.iterrows():
        raw_lon, raw_lat = r[lon_col], r[lat_col]
        name = r[name_col] if name_col else ""
        status, issues, suggestion = validate_full(raw_lon, raw_lat, src, rings)
        if status == "ok":
            n_ok += 1
        elif status == "warning":
            n_warn += 1
        else:
            n_err += 1
        issue_text = "；".join(i for i in issues if i != "正常") or "正常"

        w = g = b = ("", "")
        d_gcj = d_bd = ""
        if status != "error":
            nl, na = float(raw_lon), float(raw_lat)
            w = C.convert(nl, na, src, "wgs84")
            g = C.convert(nl, na, src, "gcj02")
            b = C.convert(nl, na, src, "bd09")
            d_gcj = round(C.haversine_m(w[0], w[1], g[0], g[1]), 1)
            d_bd = round(C.haversine_m(w[0], w[1], b[0], b[1]), 1)

        dl_rows.append({
            "name": name, "src_system": src,
            f"lon_in({src})": raw_lon, f"lat_in({src})": raw_lat,
            "lon_wgs84": fmt(w[0]) if w[0] != "" else "",
            "lat_wgs84": fmt(w[1]) if w[1] != "" else "",
            "lon_gcj02": fmt(g[0]) if g[0] != "" else "",
            "lat_gcj02": fmt(g[1]) if g[1] != "" else "",
            "lon_bd09": fmt(b[0]) if b[0] != "" else "",
            "lat_bd09": fmt(b[1]) if b[1] != "" else "",
            "gcj_vs_wgs_m": d_gcj, "bd_vs_wgs_m": d_bd,
            "status": status, "issues": issue_text, "suggestion": suggestion,
        })
        badge = {"ok": "✅ 正常", "warning": "⚠️ 警告", "error": "❌ 错误"}[status]
        dash = "—"
        show_rows.append({
            "名称": name,
            "输入(经,纬)": f"{raw_lon}, {raw_lat}",
            "WGS-84": dash if w[0] == "" else f"{fmt(w[0])}, {fmt(w[1])}",
            "GCJ-02": dash if g[0] == "" else f"{fmt(g[0])}, {fmt(g[1])}",
            "BD-09": dash if b[0] == "" else f"{fmt(b[0])}, {fmt(b[1])}",
            "偏移(米)": dash if d_gcj == "" else f"G {d_gcj} · B {d_bd}",
            "状态": badge,
            "问题/建议": issue_text,
        })
    counts = {"total": len(dl_rows), "ok": n_ok, "warn": n_warn, "err": n_err}
    return pd.DataFrame(dl_rows), pd.DataFrame(show_rows), counts


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------
st.title("🧭 坐标系转换工具")
st.caption("WGS-84 ⇄ GCJ-02 ⇄ BD-09 · 公开标准算法 · 纯离线运行，不调用任何第三方接口，不上传任何数据")

with st.expander("三个坐标系分别是谁在用？为什么会偏移几百米？", expanded=True):
    c1, c2, c3 = st.columns(3)
    c1.markdown("**WGS-84** · GPS / 国际通用  \n"
                "全球定位系统与国际地图的“真实”坐标。Google Earth、境外地图、手机原始定位、遥感影像都用它。")
    c2.markdown("**GCJ-02（火星坐标）** · 中国大陆法定加密  \n"
                "国家测绘局在 WGS-84 上施加的非线性保密偏移。高德、腾讯、Google 中国等国内地图使用。")
    c3.markdown("**BD-09** · 百度地图专用  \n"
                "百度在 GCJ-02 基础上再加一层偏移。仅百度地图 / 百度 API 使用。")
    st.info("**为什么会偏移？** 中国法规要求公开地图必须对真实坐标做保密处理，于是有了 GCJ-02，百度又叠加了 BD-09。"
            "这些偏移是**随位置变化的非线性量**（不是固定平移）——中国境内 GCJ-02 相对 WGS-84 通常偏 **300~700 米**，"
            "BD-09 可达 **1 公里以上**。不同来源的坐标直接叠到同一张图上就会“错位”几百米，必须先转到同一坐标系。"
            "境外坐标三系一致、无偏移。")

tab_single, tab_batch = st.tabs(["📍 单点转换", "📄 批量转换（上传 CSV）"])
rings = load_boundary()

# ---------------- 单点 ----------------
with tab_single:
    c1, c2, c3 = st.columns([1, 1, 1.4])
    lng = c1.text_input("经度 Longitude", "116.397128")
    lat = c2.text_input("纬度 Latitude", "39.908722")
    src = c3.selectbox("源坐标系", list(SYS_LABEL), format_func=lambda s: SYS_DESC[s])
    st.caption("经度范围 [-180, 180]，纬度范围 [-90, 90]。若纬度填了大于 90 的数，多半是经纬度写反了。")

    status, issues, suggestion = validate_full(lng, lat, src, rings)
    if status == "ok":
        st.success("✔ 校验正常")
    elif status == "warning":
        st.warning("⚠ " + "；".join(issues))
    else:
        st.error("✗ " + "；".join(issues))

    if status != "error":
        nl, na = float(lng), float(lat)
        wl, wa = C.convert(nl, na, src, "wgs84")
        rows = []
        for s in ("wgs84", "gcj02", "bd09"):
            ol, oa = C.convert(nl, na, src, s)
            off = "基准" if s == "wgs84" else f"{C.haversine_m(wl, wa, ol, oa):.1f} m"
            rows.append({"坐标系": SYS_LABEL[s] + ("（源）" if s == src else ""),
                         "经度": fmt(ol), "纬度": fmt(oa), "相对 WGS-84 偏移": off})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ---------------- 批量 ----------------
with tab_batch:
    up = st.file_uploader("上传 CSV（需含经度、纬度两列；列名含 lon/lng/经度 与 lat/纬度 即可自动识别）",
                          type=["csv"])
    cc1, cc2, cc3 = st.columns([1.2, 1, 1])
    if cc1.button("📥 载入示例数据（坐标点位_待转换）", width="stretch"):
        st.session_state["use_sample"] = True
    src_choice = cc2.selectbox("源坐标系", ["auto", "wgs84", "gcj02", "bd09"],
                               format_func=lambda s: "自动识别" if s == "auto" else SYS_LABEL[s])

    df_in = None
    try:
        if up is not None:
            df_in = read_csv_bytes(up.getvalue())
        elif st.session_state.get("use_sample"):
            df_in = pd.read_csv(io.StringIO(SAMPLE_CSV))
    except Exception as e:
        st.error(f"读取 CSV 失败：{e}")

    if df_in is None:
        st.info("请上传 CSV，或点上方“载入示例数据”试用。")
    else:
        lon_col = detect_col(df_in.columns, LON_KEYS)
        lat_col = detect_col(df_in.columns, LAT_KEYS)
        if lon_col is None or lat_col is None:
            st.error(f"无法识别经度/纬度列。现有列：{list(df_in.columns)}")
        else:
            name_col = detect_col(df_in.columns, ("name", "名称", "点位", "地点", "poi", "id"))
            src = src_choice
            if src == "auto":
                src = detect_system(lon_col) or detect_system(lat_col) or "wgs84"

            dl_df, show_df, cnt = process(df_in, name_col, lon_col, lat_col, src, rings)

            st.caption(f"识别到列：名称=`{name_col}` 经度=`{lon_col}` 纬度=`{lat_col}`；"
                       f"源坐标系=**{SYS_LABEL[src]}**")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("总点数", cnt["total"])
            m2.metric("✅ 正常", cnt["ok"])
            m3.metric("⚠️ 警告", cnt["warn"])
            m4.metric("❌ 错误", cnt["err"])

            st.dataframe(show_df, hide_index=True, width="stretch")

            csv_bytes = dl_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇ 下载结果 CSV（含三种坐标系 + 校验结论）",
                               data=csv_bytes, file_name="坐标点位_已转换.csv",
                               mime="text/csv", type="primary")

with st.sidebar:
    st.header("关于")
    st.markdown(
        "- **算法**：WGS-84↔GCJ-02 为国测局公开加密公式（Krasovsky 1940 椭球，"
        "GCJ→WGS 数值迭代反解，毫米级）；GCJ-02↔BD-09 为百度公开解析式。\n"
        "- **隐私**：所有计算在服务器端本地完成，**不调用任何第三方定位/转换 API**。\n"
        "- **校验**：自动识别经纬度写反、超范围、(0,0) 空值、境外、疑似海上等异常。\n"
        "- **海陆判断**：内置简化中国边界（射线法），仅作“疑似”提示。")
    st.caption("离线标准算法 · 可自由分享部署")

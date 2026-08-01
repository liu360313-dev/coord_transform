# -*- coding: utf-8 -*-
"""
坐标系转换核心库  ——  WGS-84 ⇄ GCJ-02 ⇄ BD-09
=================================================

只依赖标准库 math，使用**公开的标准算法**，完全离线，不调用任何联网 API。

三个坐标系简介
--------------
- WGS-84 : GPS / 国际通用的“真实”地理坐标（Google Earth、绝大多数境外地图、
           手机原始定位、遥感影像都用它）。
- GCJ-02 : 中国国家测绘局制定的加密坐标（“火星坐标系”）。中国大陆境内依法对
           WGS-84 施加一个非线性、随位置变化的偏移。高德、腾讯、Google中国、
           以及绝大多数国产地图用它。相对 WGS-84 一般偏 300~700 米。
- BD-09  : 百度在 GCJ-02 基础上**再加密一层**得到的坐标。仅百度地图/百度API使用。
           相对 GCJ-02 再偏移几十~上百米。

因此：同一个真实地点，在不同底图上直接叠加会“错位”几百米，必须做坐标系转换。

算法说明
--------
- WGS-84 ↔ GCJ-02 : 国家测绘局加密公式（业界公开的标准实现，基于 Krasovsky 1940
                    椭球）。正向为解析式；反向（GCJ→WGS）用数值迭代求解，精度可达
                    毫米级（优于常见的“二倍减”一步近似）。
- GCJ-02 ↔ BD-09  : 百度官方公开的解析互逆公式。
- 链式转换 WGS-84 ↔ BD-09 一律经由 GCJ-02 中转。

参考实现（同一套公开算法被广泛使用）：
    https://github.com/wandergis/coordtransform
    https://github.com/googollee/eviltransform
"""

import math

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
PI = 3.1415926535897932384626
X_PI = PI * 3000.0 / 180.0          # 百度公式用到的角度常量
A = 6378245.0                       # Krasovsky 1940 椭球长半轴（米）
EE = 0.00669342162296594323         # 椭球偏心率的平方

# 判定“是否在中国境内”的粗略经纬度包络框（GCJ-02 只在中国大陆生效）。
CHINA_LNG_MIN, CHINA_LNG_MAX = 72.004, 137.8347
CHINA_LAT_MIN, CHINA_LAT_MAX = 0.8293, 55.8271

VALID_SYSTEMS = ("wgs84", "gcj02", "bd09")


# ---------------------------------------------------------------------------
# 内部偏移多项式（国测局加密公式的核心）
# ---------------------------------------------------------------------------
def _transform_lat(x, y):
    ret = (-100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y
           + 0.1 * x * y + 0.2 * math.sqrt(abs(x)))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x, y):
    ret = (300.0 + x + 2.0 * y + 0.1 * x * x
           + 0.1 * x * y + 0.1 * math.sqrt(abs(x)))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def out_of_china(lng, lat):
    """是否落在中国大陆之外（此时 GCJ-02/BD-09 加密不适用，坐标应原样返回）。"""
    return not (CHINA_LNG_MIN < lng < CHINA_LNG_MAX and CHINA_LAT_MIN < lat < CHINA_LAT_MAX)


# ---------------------------------------------------------------------------
# 六种两两转换
# ---------------------------------------------------------------------------
def wgs84_to_gcj02(lng, lat):
    """WGS-84 → GCJ-02（真实坐标 → 火星坐标）。"""
    if out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
    dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng, lat, iterations=30, eps=1e-11):
    """GCJ-02 → WGS-84（火星坐标 → 真实坐标）。

    正向加密无解析逆，这里用数值迭代反解：不断用 wgs→gcj 逼近，
    收敛到毫米级，精度优于常见的一步近似 (2*lng - mglng)。
    """
    if out_of_china(lng, lat):
        return lng, lat
    wlng, wlat = lng, lat
    for _ in range(iterations):
        glng, glat = wgs84_to_gcj02(wlng, wlat)
        dlng, dlat = glng - lng, glat - lat
        wlng -= dlng
        wlat -= dlat
        if abs(dlng) < eps and abs(dlat) < eps:
            break
    return wlng, wlat


def gcj02_to_bd09(lng, lat):
    """GCJ-02 → BD-09（百度公开公式）。"""
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * X_PI)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * X_PI)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd09_to_gcj02(lng, lat):
    """BD-09 → GCJ-02（百度公开公式，解析逆）。"""
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    return z * math.cos(theta), z * math.sin(theta)


def wgs84_to_bd09(lng, lat):
    """WGS-84 → BD-09（经 GCJ-02 中转）。境外原样返回。"""
    if out_of_china(lng, lat):
        return lng, lat
    return gcj02_to_bd09(*wgs84_to_gcj02(lng, lat))


def bd09_to_wgs84(lng, lat):
    """BD-09 → WGS-84（经 GCJ-02 中转）。境外原样返回。"""
    if out_of_china(lng, lat):
        return lng, lat
    return gcj02_to_wgs84(*bd09_to_gcj02(lng, lat))


# 直接转换查找表（同系统为恒等）
_DIRECT = {
    ("wgs84", "gcj02"): wgs84_to_gcj02,
    ("gcj02", "wgs84"): gcj02_to_wgs84,
    ("gcj02", "bd09"): gcj02_to_bd09,
    ("bd09", "gcj02"): bd09_to_gcj02,
    ("wgs84", "bd09"): wgs84_to_bd09,
    ("bd09", "wgs84"): bd09_to_wgs84,
}


def convert(lng, lat, src, dst):
    """通用转换入口。src/dst ∈ {'wgs84','gcj02','bd09'}，返回 (lng, lat)。"""
    src, dst = src.lower(), dst.lower()
    if src not in VALID_SYSTEMS or dst not in VALID_SYSTEMS:
        raise ValueError(f"坐标系必须是 {VALID_SYSTEMS} 之一，收到 src={src!r}, dst={dst!r}")
    lng, lat = float(lng), float(lat)
    if src == dst:
        return lng, lat
    # GCJ-02/BD-09 的加密只在中国大陆生效；境外点在三种坐标系下数值一致，
    # 直接原样返回，避免给境外点编造不存在的偏移。
    if out_of_china(lng, lat):
        return lng, lat
    return _DIRECT[(src, dst)](lng, lat)


def convert_all(lng, lat, src):
    """把一个点转成全部三种坐标系，返回 {'wgs84':(lng,lat), 'gcj02':..., 'bd09':...}。"""
    return {sys: convert(lng, lat, src, sys) for sys in VALID_SYSTEMS}


# ---------------------------------------------------------------------------
# 距离（用于报告“偏移了多少米”）
# ---------------------------------------------------------------------------
def haversine_m(lng1, lat1, lng2, lat2):
    """两点球面距离（米）。用于度量不同坐标系之间的偏移量。"""
    r = 6371008.8  # 平均地球半径（米）
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


# ---------------------------------------------------------------------------
# 坐标合法性校验
# ---------------------------------------------------------------------------
def validate_point(lng, lat):
    """
    校验单个坐标点是否可疑/非法。返回 dict：
        status      : 'ok' | 'warning' | 'error'
        issues      : [中文问题描述, ...]
        suggestion  : 建议（如“经纬度疑似写反”）或 ''
    规则：
        error   —— 数值缺失/非数、经纬度超出全球范围（无法可靠转换）
        warning —— 疑似经纬度写反、落在中国境外、疑似 (0,0) 空值
    注意：本函数是纯数值校验；“落在海里/境外陆地”这类需要边界多边形的判断
          由 batch_convert.py 里的精细校验补充。
    """
    issues, suggestion, status = [], "", "ok"

    # 1) 数值有效性
    try:
        lng = float(lng)
        lat = float(lat)
    except (TypeError, ValueError):
        return {"status": "error", "issues": ["经度或纬度不是有效数字（缺失或非数值）"], "suggestion": ""}
    if math.isnan(lng) or math.isnan(lat):
        return {"status": "error", "issues": ["经度或纬度为空值 (NaN)"], "suggestion": ""}

    # 2) 全球范围检查
    lng_ok = -180.0 <= lng <= 180.0
    lat_ok = -90.0 <= lat <= 90.0
    if not lng_ok:
        issues.append(f"经度 {lng} 超出有效范围 [-180, 180]")
        status = "error"
    if not lat_ok:
        issues.append(f"纬度 {lat} 超出有效范围 [-90, 90]")
        status = "error"

    # 3) 经纬度疑似写反：
    #    原点不在中国、但把经纬度对调后正好落进中国 → 极可能是写反了。
    #    （典型症状：纬度 > 90，一定是把经度填到了纬度列）
    orig_in_china = lng_ok and lat_ok and not out_of_china(lng, lat)
    swapped_valid = (-180.0 <= lat <= 180.0) and (-90.0 <= lng <= 90.0)
    swapped_in_china = swapped_valid and not out_of_china(lat, lng)
    if (not orig_in_china) and swapped_in_china:
        suggestion = f"经纬度疑似写反：对调后为 (经度={lat}, 纬度={lng})，落在中国境内"
        issues.append(suggestion)
        if status != "error":
            status = "warning"

    # 4) 疑似空值 (0,0) —— 落在几内亚湾，几乎不可能是真实业务点
    if abs(lng) < 1e-9 and abs(lat) < 1e-9:
        issues.append("坐标为 (0, 0)，疑似缺失/未填写")
        if status != "error":
            status = "warning"

    # 5) 落在中国境外（数值本身合法，但 GCJ-02/BD-09 加密不适用）
    if lng_ok and lat_ok and out_of_china(lng, lat) and not (abs(lng) < 1e-9 and abs(lat) < 1e-9):
        issues.append("落在中国大陆境外：GCJ-02/BD-09 偏移不适用，转换将原样返回")
        if status == "ok":
            status = "warning"

    if not issues:
        issues.append("正常")
    return {"status": status, "issues": issues, "suggestion": suggestion}


# ---------------------------------------------------------------------------
# 自检 + 命令行单点转换
# ---------------------------------------------------------------------------
def _self_test():
    """用往返一致性 + 偏移量合理性做自检，不依赖任何硬编码参考值。"""
    # 北京天安门 WGS-84
    lng, lat = 116.397128, 39.908722

    g_lng, g_lat = wgs84_to_gcj02(lng, lat)
    b_lng, b_lat = wgs84_to_bd09(lng, lat)

    # 往返：WGS→GCJ→WGS 应回到原点（毫米级）
    r_lng, r_lat = gcj02_to_wgs84(g_lng, g_lat)
    assert haversine_m(lng, lat, r_lng, r_lat) < 0.001, "WGS↔GCJ 往返误差过大"

    # 往返：WGS→BD→WGS。BD-09↔GCJ-02 用的是百度公开的解析式，二者并非严格互逆，
    # 存在约几厘米的固有残差（业界公认特性），故用 0.5 m 容差。
    rb_lng, rb_lat = bd09_to_wgs84(b_lng, b_lat)
    assert haversine_m(lng, lat, rb_lng, rb_lat) < 0.5, "WGS↔BD 往返误差过大"

    # 偏移量应在合理量级（北京一带 GCJ 相对 WGS 约数百米）
    d_gcj = haversine_m(lng, lat, g_lng, g_lat)
    d_bd = haversine_m(lng, lat, b_lng, b_lat)
    assert 100 < d_gcj < 1000, f"GCJ 偏移异常: {d_gcj:.1f} m"
    assert 200 < d_bd < 2000, f"BD 偏移异常: {d_bd:.1f} m"

    # 境外点应原样返回（巴黎）
    assert wgs84_to_gcj02(2.352222, 48.856614) == (2.352222, 48.856614), "境外点未原样返回"

    print("[自检通过]")
    print(f"  天安门 WGS-84 : ({lng:.6f}, {lat:.6f})")
    print(f"       → GCJ-02 : ({g_lng:.6f}, {g_lat:.6f})   偏移 {d_gcj:.1f} m")
    print(f"       → BD-09  : ({b_lng:.6f}, {b_lat:.6f})   偏移 {d_bd:.1f} m")


def _cli():
    import argparse
    import sys
    try:  # Windows 终端默认 GBK，避免打印 ✗/⚠/═ 等字符时 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(
        description="WGS-84 ⇄ GCJ-02 ⇄ BD-09 单点坐标转换（离线，标准算法）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("lng", nargs="?", type=float, help="经度 longitude")
    p.add_argument("lat", nargs="?", type=float, help="纬度 latitude")
    p.add_argument("--src", default="wgs84", choices=VALID_SYSTEMS, help="源坐标系（默认 wgs84）")
    p.add_argument("--selftest", action="store_true", help="运行内置自检")
    args = p.parse_args()

    if args.selftest or args.lng is None:
        _self_test()
        return

    v = validate_point(args.lng, args.lat)
    print(f"输入 ({args.lng}, {args.lat})  源坐标系={args.src}")
    print(f"校验：{v['status'].upper()} —— {'；'.join(v['issues'])}")
    if v["status"] == "error":
        print("存在严重错误，已跳过转换。")
        return
    for sys in VALID_SYSTEMS:
        o_lng, o_lat = convert(args.lng, args.lat, args.src, sys)
        tag = "（源）" if sys == args.src else ""
        print(f"  {sys.upper():6s}: {o_lng:.7f}, {o_lat:.7f} {tag}")


if __name__ == "__main__":
    _cli()

# 🧭 坐标系转换工具 · WGS-84 ⇄ GCJ-02 ⇄ BD-09

一个可在线分享的坐标系转换小工具：支持 **单点转换** 与 **批量转换（上传 CSV → 校验 → 转换 → 下载）**，
使用**公开的标准算法**，**纯离线计算，不调用任何联网第三方 API，也不上传任何数据**。

基于 [Streamlit](https://streamlit.io) 构建，可一键部署到 **Streamlit Community Cloud** 免费分享给同事朋友。

---

## ✨ 功能

- **单点转换**：输入经纬度，选源坐标系，实时给出 WGS-84 / GCJ-02 / BD-09 三种结果及相对 WGS-84 的偏移量。
- **批量转换**：上传 CSV（自动识别经度/纬度列与源坐标系），一次转换所有点并可下载结果 CSV（UTF-8-BOM，Excel 友好）。
- **坐标异常校验**：自动发现并提示
  - 经纬度**写反**（如纬度 > 90，或对调后才落在中国境内）
  - 经纬度**超出范围**（经度 ∉ [-180,180]、纬度 ∉ [-90,90]）
  - **(0,0) 空值**（疑似缺失）
  - **落在中国境外**（GCJ-02/BD-09 偏移不适用，三系一致原样返回）
  - **疑似落在海上/境外陆地**（用内置简化中国边界做射线法判断）
- **零重依赖**：只需 `streamlit + pandas`，海陆判断用纯 Python 射线法，**无需 geopandas / GDAL**，部署快而稳。

---

## 📁 文件结构

```
.
├── streamlit_app.py            # 主程序（Streamlit 入口）
├── coord_transform.py          # 核心转换库（纯标准库，六种互转 + 校验）
├── china_boundary_gcj02.json   # 简化中国边界（GCJ-02，用于海陆/境内提示）
├── requirements.txt            # 依赖
├── .streamlit/config.toml      # 主题与上传大小配置
├── sample/
│   └── 坐标点位_待转换.csv       # 示例 CSV（也可在应用内点“载入示例”）
└── README.md
```

**输入 CSV 格式**：至少包含经度、纬度两列，列名含 `lon`/`lng`/`经度` 与 `lat`/`纬度` 即可自动识别；
若列名带坐标系后缀（如 `lon_wgs84`、`lng_gcj02`、`lat_bd09`）会自动推断源坐标系，也可在界面手动指定。示例：

```csv
name,lon_wgs84,lat_wgs84
天安门,116.397128,39.908722
上海外滩,121.490317,31.236305
```

---

## 🚀 部署到 Streamlit Community Cloud（推荐，免费）

1. **把本文件夹作为一个 GitHub 仓库**推送上去（`streamlit_app.py` 需在仓库根目录）：
   ```bash
   cd streamlit_app
   git init
   git add .
   git commit -m "坐标系转换工具 Streamlit 版"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
2. 打开 **https://share.streamlit.io** ，用 GitHub 账号登录。
3. 点击 **“New app”** → 选择你的仓库、分支 `main`、主文件填 **`streamlit_app.py`**。
4. 点击 **“Deploy”**，等待依赖安装完成，即可获得一个 `https://<名字>.streamlit.app` 的公开网址，直接分享即可。

> 之后每次 `git push`，线上应用会自动重新部署更新。

---

## 💻 本地运行

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

浏览器会自动打开 `http://localhost:8501`。

---

## 🔬 算法说明

- **WGS-84 ↔ GCJ-02**：国家测绘局公开加密公式（基于 Krasovsky 1940 椭球）。
  正向为解析式；反向（GCJ→WGS）用**数值迭代反解**，往返精度可达毫米级。
- **GCJ-02 ↔ BD-09**：百度官方公开的解析互逆公式（存在约几厘米固有残差）。
- **WGS-84 ↔ BD-09**：经 GCJ-02 中转。
- 加密只在中国大陆生效，**境外坐标三系一致、无偏移**。

参考的公开标准实现：
[wandergis/coordtransform](https://github.com/wandergis/coordtransform)、
[googollee/eviltransform](https://github.com/googollee/eviltransform)。

---

## ⚠️ 说明

- 内置简化边界仅用于“疑似海上/境外”的**提示**，非权威国界；需要精确海陆判断时，
  请配合完整边界数据与 `geopandas` 使用。
- 本工具与结果仅供技术参考，不代表任何行政区划或边界主张。

## 📄 许可

MIT License，可自由使用、修改、分享。

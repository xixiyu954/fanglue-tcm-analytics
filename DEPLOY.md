# 🚀 公网部署指南（免费上线，把链接放进简历）

本项目已完成云端零配置适配：
- 入口文件位于仓库根目录 `streamlit_app.py`；
- 原始压缩数据 `data/raw/*` 总体积 **< 2 MB**，可直接托管在 GitHub；
- 首次冷启动时 `app/core/db.py` 会自动调用 `etl/build_db.py` 在 4 秒内构建 SQLite 数据库。

---

## 当前线上实例

- **公网在线地址**：https://fanglue-tcm.streamlit.app（Streamlit Community Cloud，Python 3.12）
- **GitHub 代码仓库**：https://github.com/xixiyu954/fanglue-tcm-analytics

后续每次执行 `git push origin main`，Streamlit Community Cloud 会自动拉取最新代码重新部署。

---

## 本地修改后同步更新

```powershell
cd C:\Users\Administrator\.gemini\antigravity\scratch\fanglue
git add -A
git commit -m "chore: 更新数据或页面"
git push origin main
```

---

## 第二步：二选一免费部署到公网

### 方案 A：Streamlit Community Cloud（最简单，约 3 分钟）
1. 打开 https://share.streamlit.io 并使用 GitHub 账号登录；
2. 点击 **Create app → Deploy a public app from GitHub**；
3. 填写：
   - **Repository**：`<你的GitHub用户名>/fanglue-tcm-analytics`
   - **Branch**：`main`
   - **Main file path**：`streamlit_app.py`
4. 点击 **Deploy!**，等待 2–3 分钟安装依赖，即可获得形如 `https://fanglue-tcm.streamlit.app` 的公网链接。

> **提示**：Streamlit Community Cloud 免费实例在闲置重启后会重置本地文件系统，因此 `events` 表的长期埋点建议每 2–3 天从「SQL 实验室」或后续接入免费的 Supabase/Turso 数据库持久化。

### 方案 B：Hugging Face Spaces（Docker 部署，国内访问通常更稳）
1. 登录 https://huggingface.co → 右上角 **New Space**；
2. Space SDK 选择 **Docker**（Blank 模板），硬件选免费 CPU Basic；
3. 把本仓库代码推送到该 Space 仓库（项目根目录下已准备好 `Dockerfile`，监听 Hugging Face 默认端口 `7860`，并会在构建镜像时预先建好数据库）；
4. 构建完成后即可获得 `https://huggingface.co/spaces/<用户名>/<space名>` 公网访问地址。

---

## 第三步：收集真实埋点并产出简历级分析报告

1. 上线后把链接发到班级群 / 中药专业学习群，邀请 20–50 位同学试用 2 周（比如用来做方剂复习、查配伍禁忌、跑网络药理学课程作业）；
2. 在「📈 用户行为分析」页面关闭模拟数据开关，查看真实漏斗、页面偏好与回访；
3. 按 `reports/分析报告模板.md` 填入真实指标与图表截图，与在线链接一起放进简历。

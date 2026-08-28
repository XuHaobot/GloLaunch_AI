# GloLaunch AI 快速启动指南

## 双击启动（推荐新手）

### `start.bat` — 一键全量启动
```
双击 start.bat → 自动检测环境 → 安装依赖 → 启动后端 + 前端 → 打开浏览器
```

**功能：**
- ✅ 自动检测 Python / Node.js 是否安装
- ✅ 依赖未安装时自动执行 `pip install` / `npm install`
- ✅ 清理端口占用（8000 / 5173）
- ✅ 启动后端 FastAPI（热重载）和前端 Vite（HMR）
- ✅ 自动打开浏览器访问前台工作台
- ✅ 每个服务独立终端窗口，关闭窗口即停止

---

## 命令行启动（开发调试）

### `dev.bat` — 可选参数启动
```bash
.\dev.bat             # 同时启动前后端
.\dev.bat backend     # 仅启动后端
.\dev.bat frontend    # 仅启动前端
.\dev.bat both        # 同时启动（同默认）
```

**适用场景：**
- 调试时只重启后端或前端其中一个服务
- 需要在父终端手动管理多个子进程
- 想更灵活地控制启动顺序

---

## 手动启动（进阶用户）

### 后端
```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 前端
```bash
cd frontend
npm run dev
```

---

## 验证服务

- **健康检查**: http://localhost:8000/
- **API 文档**: http://localhost:8000/docs
- **工作台**: http://localhost:5174（Vite 可能动态分配端口）

---

## 常见问题

**Q: 为什么启动后提示 "端口被占用"？**  
A: 之前的进程没清理干净。关掉旧终端或运行 `dev.bat` 会自动杀进程再启动。

**Q: 如何切换深浅主题？**  
A: 双击启动后，在侧边栏底部点击开关即可，设置会持久化到浏览器。

**Q: npm install 很慢怎么办？**  
A: 使用国内镜像：`npm config set registry https://registry.npmmirror.com`

**Q: Python 报 ModuleNotFoundError？**  
A: 确保在虚拟环境中运行：`python -m venv venv && venv\Scripts\activate`

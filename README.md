# OpenAI 中转站纯血检测器

一个本地运行的 OpenAI 中转站检测工具，支持两种使用方式：

- 命令行检测
- 本地浏览器仪表盘

它会同时探测 `/v1/chat/completions` 和 `/v1/responses`，再根据成功响应结构、错误响应结构、流式行为等规则，对目标中转站给出一个启发式判断：

- `High probability native`
- `Suspicious; compatibility layer or response rewriting likely`
- `Clearly non-native`

这个工具判断的是“协议行为是否像 OpenAI 原生接口”，不是数学意义上的上游归属证明。

## 功能

- 检测 `/v1/chat/completions`
- 检测 `/v1/responses`
- 可选流式探针
- 模型列表拉取
- 总分、结论、逐项检查明细
- 中文本地网页界面

## 项目结构

```text
.
├─ app.py
├─ pureblood_check.py
├─ requirements.txt
├─ templates/
│  └─ index.html
├─ static/
│  ├─ app.js
│  └─ style.css
├─ tests/
│  ├─ test_app.py
│  └─ test_pureblood_check.py
└─ docs/
   └─ superpowers/
```

## 环境要求

- Python 3.13 或更高版本

## 安装依赖

```bash
python -m pip install -r requirements.txt
```

## 启动网页界面

```bash
python app.py
```

默认访问地址：

- [http://127.0.0.1:5000/](http://127.0.0.1:5000/)

页面支持：

- 输入中转站基础地址
- 输入 API Key
- 拉取模型列表
- 手动覆盖模型名
- 启用或关闭流式探针
- 查看总分、结论、probe 卡片和逐条检查细节

## 命令行用法

```bash
python pureblood_check.py --base-url https://example.com --api-key sk-xxx --model gpt-5.4 --stream
```

常用参数：

- `--base-url`
- `--api-key`
- `--model`
- `--stream`
- `--timeout`

查看帮助：

```bash
python pureblood_check.py --help
```

## 检测逻辑说明

当前规则主要看这些信号：

- 正常请求是否返回符合 OpenAI 风格的 JSON 结构
- 错误请求是否返回符合 OpenAI 风格的错误体
- 流式响应是否符合 SSE 事件格式
- `/responses` 行为是否像原生接口

这套规则更适合回答：

- “这个中转站看起来像不像 OpenAI 原生接口？”

不适合回答：

- “这个中转站一定就是官方上游吗？”

## 运行测试

```bash
pytest tests -v
```

## 本地校验

Python 语法检查：

```bash
python -m py_compile pureblood_check.py app.py
```

前端脚本语法检查：

```bash
node --check static/app.js
```

## 安全提醒

- 不要把真实 API Key 提交到 GitHub
- 如果你曾经在终端、截图、聊天记录里暴露过密钥，建议立刻更换
- 当前网页版本不会把 Key 持久化到本地文件，但你仍然应该把仓库内容和运行日志当成敏感环境处理

## 适合继续扩展的方向

- 把结论文案翻译成中文
- 给检查项加“人话别名”
- 支持多个模型或多个中转站对比
- 支持导出 JSON 报告
- 支持保存最近一次检测结果

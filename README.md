# ArxivDigest — Personalized Research Paper Pipeline

一个个性化论文推送与阅读管理系统，两板块 + 两阶段评分 + 长期反馈闭环。

- **每日 arXiv 推送**（按研究兴趣 LLM 打分，命题级匹配而非关键词匹配）
- **经典论文推荐**（Claude Opus 4.6 生成 + 过期 queue 复活）
- **两阶段评分**（扫描后 Stage-1 → 精读后 Stage-2 → 沉淀 Library）

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│  📰 Daily Digest (每天新论文)                        │
│  ├─ Top 2 Core + 3 Transfer                         │
│  └─ Classic Papers (10 篇，每周更新)                │
│                                                     │
│  操作：Stage-1 打分（扫描后初评）                   │
│                                                     │
│  ≥7 分 ──┐                                          │
└──────────┼─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────┐
│  📖 Reading Queue (Stage-1 ≥7，待精读)              │
│  操作：Stage-2 打分（精读后终评）                   │
│                                                     │
│  ≥7 分 ──┐         ≤6 丢弃                          │
│          ↓         30 天未精读 → 进 Classics 池     │
└──────────┼─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────┐
│  📚 My Library (Stage-2 ≥7，已精读沉淀)             │
│  搜索 + 排序 + 备注                                 │
│  你的个人文献库                                      │
└─────────────────────────────────────────────────────┘
```

## 日常流程

### 每天第一次使用 — 完整流程

```bash
cd src
conda activate research_paper
python action.py --config ../config.yaml
```

会做：
1. 拉 arXiv `cs` 当日新论文（缓存到 `src/data/`）
2. 检查 `src/data/scored_YYYY-MM-DD.json`：今天打过分就直接读，没打过就 LLM 并发打分（~2 分钟，~$0.20）
3. 检查 `classics_cache.json`（7 天 TTL），过期则重新生成 10 篇
4. 生成 **3 个 HTML 文件**：`digest.html`、`queue.html`、`library.html`
5. 启动反馈服务器（`http://127.0.0.1:5005`）
6. 自动打开浏览器
7. 你点击打分 → 按 Ctrl+C 退出

### 同一天再次使用 — 只开服务器就好

如果 action.py 已经跑过了、只是想继续打分或看 queue/library：

```bash
cd src
conda activate research_paper
python feedback_server.py
```

然后手动打开浏览器：
```bash
open digest.html   # 或 queue.html / library.html
```

⚠️ 区别：
- **`action.py`** = 全流程（生成 HTML + 起服务器 + 开浏览器），会走一遍缓存检查
- **`feedback_server.py`** = **只起服务器**，零 LLM 调用，秒起

想打分就必须有服务器在跑，否则：
- Queue / Library 页加载不出数据
- 打分按钮显示 `✗ server not running`

### 小贴士 — shell alias

在 `~/.zshrc` 加：

```bash
alias paper="cd /Users/pushuying/Desktop/Research/ArxivDigest/src && conda activate research_paper && python action.py --config ../config.yaml"
alias paper-serve="cd /Users/pushuying/Desktop/Research/ArxivDigest/src && conda activate research_paper && python feedback_server.py"
```

之后：
- `paper` = 每天第一次用
- `paper-serve` = 同一天再用（只起服务器）

### 命令行参数

```bash
python action.py --config ../config.yaml [选项]

  --refresh-classics    强制刷新经典论文（忽略 30 天缓存）
  --no-classics         跳过经典板块
```

### 重新打分（prompt/interest 改动后）

如果你修改了 `config.yaml` 的 interest 或 `relevancy_prompt.txt`，同一天的打分缓存不会自动失效。手动清除后重跑：

```bash
rm src/data/scored_$(date +%Y-%m-%d).json
python action.py --config ../config.yaml
```

## 两阶段评分逻辑

### Stage 1 — 扫描后初评（Daily 页）

你在 Daily digest 里看 title + abstract（~5 分钟/篇），给 1-10 分：

| 打分 | 含义 | 结果 |
|---|---|---|
| **1-6** | 不感兴趣 / 一般 | 丢弃，永不出现 |
| **7-10** | 值得精读 | 自动进 **Reading Queue** |

### Stage 2 — 精读后终评（Queue 页）

精读完整论文后，给最终评分：

| 打分 | 含义 | 结果 |
|---|---|---|
| **1-6** | 实际读完觉得一般 | 从 queue 移除，不进 library |
| **7-10** | 真正有价值 | 进 **My Library** 长期沉淀 |

### Queue 过期机制

Stage-1 评分后 30 天未进行 Stage-2 → 从 queue 消失，**进入下次 Classics 刷新的候选池**，可能以"经典"身份被捞回。

## 数据文件

| 文件 | 位置 | 说明 |
|---|---|---|
| `config.yaml` | 根目录 | 你的研究兴趣配置 |
| `feedback.jsonl` | 根目录 | 所有打分记录（append-only，每行含 `arxiv_id / rating / stage / timestamp / comment`） |
| `papers_metadata.jsonl` | 根目录 | 打过分论文的完整元数据快照（append-only，取最新） |
| `classics_cache.json` | 根目录 | 经典论文缓存（7 天 TTL） |
| `src/data/cs_<date>.jsonl` | src/data/ | arXiv 当日爬取缓存 |
| `src/data/scored_<date>.json` | src/data/ | 当日 LLM 打分缓存（7 天自动清理） |
| `digest.html` | 根目录 | Daily 页（每次运行重新生成） |
| `queue.html` | 根目录 | Queue 页（JS 从 server 实时拉数据） |
| `library.html` | 根目录 | Library 页（JS 从 server 实时拉数据，支持搜索） |

## 项目结构

```
ArxivDigest/
├── README.md
├── config.yaml
├── requirements.txt
├── feedback.jsonl             # 评分记录
├── papers_metadata.jsonl      # 论文元数据存档
├── classics_cache.json        # 7 天 TTL
└── src/
    ├── action.py              # 主入口
    ├── download_new_papers.py # arXiv 爬取
    ├── relevancy.py           # LLM 双打分（并发）
    ├── relevancy_prompt.txt   # 打分 rubric
    ├── industry.py            # 大厂动态模块（保留备用，Daily 不再调用）
    ├── classics.py            # 经典论文模块（Claude Opus 4.6）
    ├── feedback_server.py     # Flask 反馈服务器
    ├── utils.py               # OpenAI client 封装
    └── data/
        ├── cs_<date>.jsonl    # arXiv 爬取缓存
        └── scored_<date>.json # 每日打分缓存
```

## 配置

### 1. Python 环境

```bash
conda create -n research_paper python=3.10 -y
conda activate research_paper
pip install -r requirements.txt
```

### 2. API 密钥

```bash
# OpenRouter (所有 LLM 调用统一走 OpenRouter)
export OPENROUTER_API_KEY=sk-or-v1-xxx
```

### 3. 修改 `config.yaml`

```yaml
topic: "Computer Science"
categories: ["Artificial Intelligence", "Computation and Language", "Machine Learning", "Multiagent Systems"]
threshold: 6  # 暂无实际作用，保留兼容
interest: |
  （用英文描述你的研究方向，按"命题链 + 分级评分指引"格式。示例见当前 config.yaml）
```

### 4. 预填种子论文（可选）

在 `feedback.jsonl` 添加带 `stage: 2, rating: 10` 的种子，同时在 `papers_metadata.jsonl` 补全元数据，这些会直接出现在 Library 冷启动。

## 打分管线 — 命题匹配机制

LLM 打分时会执行一个**命题 vs 关键词的强制二分检查**：

1. 提取论文的 core scientific question（一句话）
2. 与你在 `config.yaml` 中定义的研究命题链对比
3. 如果只是表面关键词重叠（如 "LLM + agent + scaling"），core_score 上限 4

`config.yaml` 的 interest 字段按三级指引组织：
- **STRONGLY RELEVANT (8-10)**：命题正中
- **ADJACENT (5-7)**：方法论可借鉴
- **NOT MY DIRECTION (1-4)**：关键词重叠但命题错位

累计 ≥5 条 Stage-1 评分后，LLM 打分会注入正反例 few-shot（含你的评分理由），推送质量逐步提升。

## 模型 & 成本

| 任务 | 模型 | API | 频率 | 月成本 |
|---|---|---|---|---|
| Daily 论文打分 | `gpt-4o-mini` | OpenAI | 每天 | ~$6 |
| Classics 论文打分 | `gpt-4o-mini` | OpenAI | 每周 | ~$0.01 |
| **Classics 候选生成** | **`anthropic/claude-opus-4.6`** | **OpenRouter** | 每周 | ~$0.04 |

**总月成本 ≈ $6**（按每天跑一次 Daily 估算）。

## 默认参数

| 参数 | 值 | 位置 |
|---|---|---|
| Daily 论文数 | 2 core + 3 transfer | `action.py select_top_papers()` |
| 每批打分数 | 16 | `action.py num_paper_in_prompt` |
| 并发度 | 8 | `relevancy.py MAX_CONCURRENCY` |
| 反馈激活阈值 | 5 条 | `relevancy.py FEEDBACK_MIN` |
| Classics TTL | 30 天 | `classics.py CACHE_TTL_DAYS` |
| Classics 每周 top-k | 10 | `classics.py TOP_K` |
| Classics LLM 候选数 | 25 | `classics.py LLM_CANDIDATE_COUNT` |
| Queue 过期天数 | 30 天 | `feedback_server.py QUEUE_EXPIRY_DAYS` |
| Queue 入库阈值 | 7 | `feedback_server.py QUEUE_MIN_RATING` |
| Library 入库阈值 | 7 | `feedback_server.py LIBRARY_MIN_RATING` |
| 反馈服务器端口 | 5005 | `feedback_server.py` |
| Scored cache 保留 | 7 天 | `action.py` purge 逻辑 |

## 工作流建议

1. **每天 1 小时**：跑 `action.py`，扫 Daily 的 5 篇 + Classics 若干
2. **快速打分（Stage-1）**：读 abstract 5-6 分钟，打 1-10 分
3. **每周精读 3 篇**：在 Reading Queue 里挑最想读的，精读后打 Stage-2 分
4. **沉淀到 Library**：Stage-2 ≥7 的论文自动进 library，以后写论文可搜索引用

**反馈闭环激活**：累计 ≥5 条 Stage-1 评分后，LLM 打分会参考你的口味（正反例 + 评分理由作为 few-shot 注入 prompt），推送质量会逐步提升。

## 已知限制

- **Daily 打分缓存只按日期**：同一天 prompt 改了也不会重新打分，需要手动 `rm src/data/scored_<今天>.json`
- **Classics 可能命中重复论文**：LLM 生成的 arxiv ID 和验证、SS 扩展之间可能出现你已在 Library 的论文，会被过滤但偶尔有漏网
- **反馈种子 ID 不一定真实**：`seed-amem` / `seed-aplan` 是占位 ID，不对应真实 arXiv 论文；`2603.01896` 是用户提供的真实 ID

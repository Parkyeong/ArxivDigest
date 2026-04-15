# ArxivDigest — Personalized Research Paper Pipeline

一个个性化论文推送与阅读管理系统，三板块 + 两阶段评分 + 长期反馈闭环。

- **每日 arXiv 推送**（按研究兴趣 LLM 打分）
- **大厂动态追踪**（OpenAI / Anthropic / DeepMind / Meta FAIR / MSR 近 14 天发布）
- **经典论文推荐**（Claude Opus 4.6 生成 + 过期 queue 复活）
- **两阶段评分**（扫描后 Stage-1 → 精读后 Stage-2 → 沉淀 Library）

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│  📰 Daily Digest (每天新论文)                        │
│  ├─ Top 2 Core + 3 Transfer                         │
│  ├─ Industry Highlights (5 家大厂，每家 ≤3 篇)      │
│  └─ Classic Papers (10 篇，每月更新)                │
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

## 一键运行

```bash
cd src
conda activate research_paper
python action.py --config ../config.yaml
```

首次跑流程（~2 分钟）：
1. 拉 arXiv `cs` 当日新论文（缓存到 `src/data/`）
2. 检查 `src/data/scored_YYYY-MM-DD.json`：今天打过分就直接读，没打过就 LLM 并发打分
3. 检查 `industry_cache.json`（7 天 TTL），过期则重抓 + 重打分
4. 检查 `classics_cache.json`（30 天 TTL），过期则重新生成 10 篇
5. 生成 **3 个 HTML 文件**：`digest.html`、`queue.html`、`library.html`
6. 启动反馈服务器（`http://127.0.0.1:5005`）
7. 自动打开浏览器
8. 你点击打分，按 Ctrl+C 退出

### 命令行参数

```bash
python action.py --config ../config.yaml [选项]

  --refresh-industry    强制刷新大厂数据（忽略 7 天缓存）
  --no-industry         跳过大厂板块
  --refresh-classics    强制刷新经典论文（忽略 30 天缓存）
  --no-classics         跳过经典板块
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
| `industry_cache.json` | 根目录 | 大厂动态缓存（7 天 TTL） |
| `classics_cache.json` | 根目录 | 经典论文缓存（30 天 TTL） |
| `src/data/cs_<date>.jsonl` | src/data/ | arXiv 当日爬取缓存 |
| `src/data/scored_<date>.json` | src/data/ | 当日 LLM 打分缓存（7 天自动清理） |
| `src/digest.html` | src/ | Daily 页（每次运行重新生成） |
| `src/queue.html` | src/ | Queue 页（JS 从 server 实时拉数据） |
| `src/library.html` | src/ | Library 页（JS 从 server 实时拉数据，支持搜索） |

## 项目结构

```
ArxivDigest/
├── README.md
├── config.yaml
├── requirements.txt
├── feedback.jsonl             # 评分记录
├── papers_metadata.jsonl      # 论文元数据存档
├── industry_cache.json        # 7 天 TTL
├── classics_cache.json        # 30 天 TTL
└── src/
    ├── action.py              # 主入口
    ├── download_new_papers.py # arXiv 爬取
    ├── relevancy.py           # LLM 双打分（并发）
    ├── relevancy_prompt.txt   # 打分 rubric
    ├── industry.py            # 大厂动态模块
    ├── classics.py            # 经典论文模块（Claude Opus 4.6）
    ├── feedback_server.py     # Flask 反馈服务器
    ├── utils.py               # OpenAI client 封装
    ├── digest.html            # 生成的日报
    ├── queue.html             # 生成的 queue
    ├── library.html           # 生成的 library
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
# OpenAI (daily / industry / classics 打分)
export OPENAI_API_KEY=sk-xxx

# OpenRouter (classics 生成用 Claude Opus 4.6)
export OPENROUTER_API_KEY=sk-or-v1-xxx
```

### 3. 修改 `config.yaml`

```yaml
topic: "Computer Science"
categories: ["Artificial Intelligence", "Computation and Language", "Machine Learning", "Multiagent Systems"]
threshold: 6  # 暂无实际作用，保留兼容
interest: |
  （用英文描述你的研究方向。示例见当前 config.yaml）
```

### 4. 预填种子论文（可选）

在 `feedback.jsonl` 添加带 `stage: 2, rating: 10` 的种子，同时在 `papers_metadata.jsonl` 补全元数据，这些会直接出现在 Library 冷启动。

## 模型 & 成本

| 任务 | 模型 | API | 频率 | 月成本 |
|---|---|---|---|---|
| Daily 论文打分 | `gpt-4o-mini` | OpenAI | 每天 | ~$6 |
| Industry 论文打分 | `gpt-4o-mini` | OpenAI | 每周 | ~$0.10 |
| Classics 论文打分 | `gpt-4o-mini` | OpenAI | 每月 | ~$0.01 |
| **Classics 候选生成** | **`anthropic/claude-opus-4.6`** | **OpenRouter** | 每月 | ~$0.04 |

**总月成本 ≈ $6-7**（按每天跑一次 Daily 估算）。

## 默认参数

| 参数 | 值 | 位置 |
|---|---|---|
| Daily 论文数 | 2 core + 3 transfer | `action.py select_top_papers()` |
| 每批打分数 | 16 | `action.py num_paper_in_prompt` |
| 并发度 | 8 | `relevancy.py MAX_CONCURRENCY` |
| 反馈激活阈值 | 5 条 | `relevancy.py FEEDBACK_MIN` |
| Industry TTL | 7 天 | `industry.py CACHE_TTL_DAYS` |
| Industry 窗口 | 14 天 | `industry.py WINDOW_DAYS` |
| Industry 每家 top-k | 3 | `industry.py TOP_K_PER_LAB` |
| Classics TTL | 30 天 | `classics.py CACHE_TTL_DAYS` |
| Classics 每月 top-k | 10 | `classics.py TOP_K` |
| Classics LLM 候选数 | 25 | `classics.py LLM_CANDIDATE_COUNT` |
| Queue 过期天数 | 30 天 | `feedback_server.py QUEUE_EXPIRY_DAYS` |
| Queue 入库阈值 | 7 | `feedback_server.py QUEUE_MIN_RATING` |
| Library 入库阈值 | 7 | `feedback_server.py LIBRARY_MIN_RATING` |
| 反馈服务器端口 | 5005 | `feedback_server.py` |
| Scored cache 保留 | 7 天 | `action.py` purge 逻辑 |

## 工作流建议

1. **每天 1 小时**：跑 `action.py`，扫 Daily 的 5 篇 + Industry 各家 + Classics 若干
2. **快速打分（Stage-1）**：读 abstract 5-6 分钟，打 1-10 分
3. **每周精读 3 篇**：在 Reading Queue 里挑最想读的，精读后打 Stage-2 分
4. **沉淀到 Library**：Stage-2 ≥7 的论文自动进 library，以后写论文可搜索引用

**反馈闭环激活**：累计 ≥5 条评分后，LLM 打分会参考你的口味（正反例作为 few-shot 注入 prompt），推送质量会逐步提升。

## 已知限制

- **大厂作者匹配精度有限**：arxiv 作者字段不带机构名，DeepMind / Meta / MSR 用宽松匹配 + LLM 兜底
- **OpenAI / Anthropic sitemap 方案**准确但只提供标题+描述（没有完整 abstract）
- **Daily 打分缓存只按日期**：同一天 prompt 改了也不会重新打分，需要手动 `rm src/data/scored_<今天>.json`
- **Classics 可能命中重复论文**：LLM 生成的 arxiv ID 和验证、SS 扩展之间可能出现你已在 Library 的论文，会被过滤但偶尔有漏网
- **反馈种子 ID 不一定真实**：`seed-amem` / `seed-aplan` 是占位 ID，不对应真实 arXiv 论文；`2603.01896` 是用户提供的真实 ID

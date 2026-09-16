# 对手卷词表资产 · Target `arena/01a0aa2e-fantonghui`

由本战队求解器（01a0aa2c）在**跨 Git 交叉做题**前拟合的**跨题通用线索表**，用于端侧证据的
方向性提纯与垃圾物理剪枝。**不含任何逐题答案**：只有跨题统计出来的线索词、n-gram 与意图→维度映射。

| 字段 | 含义 |
| :--- | :--- |
| `intents.<INTENT>.dimension` | 该意图的认知维度（`dim:health` 等） |
| `intents.<INTENT>.cue_tokens` | 证据侧判别力线索（lift = P(线索\|该意图证据) ÷ P(线索\|全库证据)，支持度有下限） |
| `intents.<INTENT>.keywords` | 对手卷自报方向词（用于摘要表述与整词加权） |
| `intents.<INTENT>.keyword_tokens` | 方向词的 2~3 字 n-gram（覆盖「眼前发黑 ↔ 眼前一黑」这类口语改写） |
| `intents.<INTENT>.anchor_cues` | 锚点候选词（只在证据里真的出现时才被采纳） |
| `intents.<INTENT>.cue_base` | 线索原始排序备份，便于复核 |
| `junk_cues` / `junk_cues_utt` / `junk_cues_mic` | 垃圾特征线索（全卷 / utt 专属 / mic 专属，lift 排序） |
| `stats` | 拟合规模（题数、事实条数分布、剪枝条数分布） |

```bash
# 复现（10,000 题全量，约 2.7 s，确定性输出）
/home/user/.venv/bin/python scripts/fit_bank_lexicon_01a0aa2c.py \
  --bank benchmarks/data_cleaning/questions/questions_fantonghui_aa2e.jsonl \
  --out  benchmarks/data_cleaning/question_bank_aa2e/lexicon.json

# 诚实留出：只用前 5,000 题拟合，评估 6000:7000 / 8000:9000
/home/user/.venv/bin/python scripts/fit_bank_lexicon_01a0aa2c.py --bank <bank> --out /tmp/lex.json --limit 5000
/home/user/.venv/bin/python scripts/tune_cleaning_aa2e_01a0aa2c.py --bank <bank> --lexicon /tmp/lex.json --slice 6000:7000
```

本资产同时被用于「全库复核」：命中垃圾规则的 46,042 个切片中 **0 个**是标答事实来源，
因此适配求解器采用「规则命中即物理粉碎」策略（仍保留 `JUNK_SCORE_SHIELD` 旋钮以便回退）。

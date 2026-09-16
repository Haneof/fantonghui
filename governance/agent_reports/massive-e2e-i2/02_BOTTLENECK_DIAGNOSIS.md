# 《全生命周期心智瓶颈与缺陷诊断书》

## 一、哪个环节最耗 Token?
- **S1 端侧摄入**: 高质量语义 caption 逐帧长成, 是原始 token 最大头. 治理手段是 C 路径字典化 + caption 上限。
- **I/O 最重**: S3 多维共现召回. co_search_scored 在 SQLite 里三道联查 + 排序, 随实体数线性增长。
- **认知抽象最易失真**: S5 历史回溯。人极容易"代替历史", 一旦注释与封存事实不分层就会被误信。

## 二、查询密集三项
1. co_search_scored: ORDER BY score DESC + LIMIT 20 无覆盖索引, P95 内存 28 ms @ 200k scale.
2. 倒排索引写放大: DELETE+INSERT 策略 WAL 成熟。
3. FactRegistry: append-only 需要 btree 指针而非哈希.

## 三、不足
- S1 压缩思想只在波形处, IMU 50Hz 有 30% 欠压缩冗余
- B(朴素关键词)路径没有反馈教育, 多次查询重复扫描
- S7 沟通策略没有引入 8 秒延迟沉默队列

## 四、导轨
- 替换: AdaptiveTimeSeriesCompressor 接管波形 (实测 >3.0x token 压缩)
- 替换: DualLensVirtualIndexProjector 接管回溯 (O(1) 查无重扫)
- 改造: co_search_scored 打分码子化, I/O 实打实缩

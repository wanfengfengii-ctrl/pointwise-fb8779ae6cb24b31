# 修复说明：停源复测误放行

## 简短根因

初版站件正文（`evidence/issue.py` 的 `_packet_body`）只在门槛 0 调用一次
`inspect_terminals`，把该门槛的公开端口连通分组作为唯一一组 `groups` 发出；
中心侧 `analysis/compose.py` 的 `_groups_at` 又在每个门槛复用这同一分组，
仅按当层分数过滤端点。这样低分隔点（如左幅中间行的 1 分像元、右幅初版中心
的 5 分像元）在高门槛失活后，分组仍把两个 7 分探针端口并为同一连通分量，
于是 6 分复测误判上限 7、「放行」；同一缺陷也使右幅 5 分与 3 分两个修订
产生完全相同的站件正文，丢失修订间的真实连通差异。

## 修复内容

- `evidence/terminals.py`：新增 `terminal_layers(layout, revision)`，对 0 至
  100 每个整数门槛复用既有 `inspect_terminals`（底层仍是四邻接
  `active_components`）产出公开端口的活动状态与幅内真实连通分组。
  `inspect_terminals` 等既有接口签名与行为不变。
- `evidence/issue.py`：站件 V1 外层字段不变，正文改为
  `{"ports": 公开端口冻结分数, "layers": [门槛0..100 各层分组]}`；内部像元
  坐标与逐点分数仍留站，正文只含公开端口事实。
- `analysis/compose.py`：停源后只读固定站件与固定清单。按请求门槛直接取
  对应层分组（不再从门槛 0 分组推断），与许可接缝（曼哈顿距离 1、同时活动
  的正对端口）合并后 BFS，允许出幅再入。正文解析改为严格校验：字段恰为
  `ports`/`layers`、层数恰为 101、每层活动端口与分数门槛完全一致、层间随
  门槛上升只收缩且每个分组只能落入上一层某个分组（只能分裂不能合并），
  任何不一致都抛 `ValueError`，且发生在发布事务写入之前。
- 裁决口径不变：二分取 0..100 中仍连通的最大整数为 `ceiling`，恰达请求
  门槛即 `passed`；零分可通记为上限 0、放行，始终不通记为 `None`、补测。
- 接口、V1 站件外层、信封校验、运行清单（`.pointwise-runtime.json`）和全部
  原断言均保留；SQLite 表结构与发布三记录同事务回滚行为未改。

## 交接要点

- 新报告只在合法签发时落库；缺幅、重复幅、混单、未接纳身份、非法请求或
  不可分析正文（含新的分层校验失败）均不产生报告、发布回执或交班摘录。
- 旧报告按原报告号领取，仍绑定各自父件（接纳号、站件号、修订号），勘误
  改选只影响新报告；`reports.readback.retrieve` 未知正整数号返回 `None`。
- 站端与中心库均可重复初始化，已有业务记录保留。

## 新增回归（`tests/test_fix_layers.py`）

1. 站件正文含 101 层，逐层与独立四邻接参考实现一致，层间只收缩/分裂；
   初版东幅上下端口在 0..5 连通、6 起拆为单端口组；勘误后仅 0..3 连通，
   两份正文不再相同。
2. 内部隔点卡 4 分、0 分、缺测三种情形，离线全门槛结果分别给出上限 4、
   上限 0（零分可通，放行）、`None`（始终不通，补测）。
3. 停源后 0..100 全门槛与全局洪泛 oracle（`tests/test_oracle.grid_reachable`）
   逐门槛起伏一致，初版可通门槛为 0..5、勘误后为 0..3。
4. 六类篡改正文（旧 `groups` 格式、层数不足、丢端口、跨层合并、未知端口、
   端口重复）全部在签发时报 `ValueError`，重开库后三张发布表仍为空；
   合法站件仍可正常签发。

## 实测说明（项目根目录，Python 3.11 标准库）

```sh
python3 -B check_project.py        # 29 tests OK（原 25 + 新增 4）
python3 -B demo.py                 # 报告1 上限5 补测；报告2 上限3 补测
python3 -B -m unittest tests.test_review.ReviewTests.test_reentry
python3 -B -m unittest discover -s tests -t .
```

实测 `check_project.py` 退出 0，`TEST SUMMARY ... result=PASS`；`demo.py`
打印两份定稿 `actual=[5, 3]`、动作均为「补测」，旧号父件仍指向初版站件。

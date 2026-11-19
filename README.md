# 澄浦薄膜导通复测台账

澄浦薄膜试验站的扫描员接收已配准的分幅置信栅格，冻结指定修订并发行站件。扫描工位停机后，夜班复测室用已接纳的站件判断两枚探针是否达到放行门槛。白班勘误另建修订，交班人员凭确切报告号领取原结论和依据。

## 运行

使用 Python 3.11 标准库，在项目根目录运行。

```sh
python3 -B check_project.py
python3 -B demo.py
```

完整套件也可直接运行 `python3 -B -m unittest discover -s tests -t .`。演示和测试使用各自的临时目录。控制台物化时提供 `check_project.py`。

## 一次复测的调用顺序

1. 站端打开 SQLite 连接，依次调用 `survey.catalog.initialize_catalog`、`survey.revisions.initialize_revision_store` 和 `evidence.packets.initialize_packet_store`。复测室在另一个库调用 `intake.records.initialize_intake_store` 和 `reports.archive.initialize_report_archive`。同一文件可以重新初始化，已有业务记录保留。
2. 调用 `survey.catalog.register(station, layout)` 登记 `SurveyLayout`，返回调查号。清单约定全局矩形、公开探针和允许接缝。`SurveyLayout.to_json()` 和 `SurveyLayout.from_json(text)` 传递固定清单。同号同内容可重投，同号异内容拒绝。
3. 调用 `survey.freeze.freeze_grid(station, survey_id, tile_id, rows)` 冻结扫描并得到修订号。勘误使用相同入口取得新号。`survey.revisions.load_revision` 按精确号领取本站栅格。`evidence.terminals.inspect_terminals(layout, revision, threshold)` 查看指定门槛的活动公开端口分组，单个活动端口也占一组。
4. 调用 `evidence.issue.issue(station, revision_id)` 得到 `IssuedPacket`。发送其 `payload` 文本。`evidence.readback.read_station_packet(station, packet_id)` 可领回相同文本及出处。站件 V1 外层使用 `version`、`survey_id`、`layout_digest`、`tile_id`、`revision_id`、`packet_id` 和 `body`。`body` 是站件分析正文，接纳者保留原文。清单摘要用于核对固定版图身份。
5. 调用 `intake.accept.accept(center, layout, payload)` 核对清单和站件，取得 `AcceptanceReceipt`。同一载荷重投可用原回执。`intake.records.load_acceptance(center, acceptance_id)` 领取固定载荷和回执。保存后的站件与清单可在停源状态使用。
6. 调用 `reports.publish.review_issue(center, survey_id, acceptance_ids, probe_a, probe_b, threshold)`，为清单指定的每幅恰选一件。返回 `ReportRecord`，其中 `decision.ceiling` 为最高可通门槛或 `None`，`decision.passed` 为布尔裁决。`parents` 固定每幅的接纳号、站件号及修订号，输入换序时父件仍按幅号排列。
7. 右幅勘误后，冻结、发行、接纳并显式改选新件，再签发一份报告。复测室重开后调用 `reports.readback.retrieve(center, report_id)` 按号领取原裁决、父件、发布回执及交班摘录。未知正整数报告号返回 `None`。

写入口自行管理 SQLite 事务，调用者交付空闲连接，同一连接上的调用顺序执行。标识为不透明编号。版本、格式、几何、分值或请求非法时报 `ValueError`。按号读取不存在的清单、修订、站件或接纳记录时报 `KeyError`。签发时缺幅、重复幅、混单、未接纳身份或不可分析的正文报 `ValueError`。SQLite 写入及提交错误向调用者返回异常，发布事务中的报告、发布回执和交班摘录一起回滚。

## 计算口径

`TileBounds(tile_id, x, y, width, height)` 指全局左上像元和正的列数、行数。`PortRef(tile_id, x, y)` 指一个全局像元。探针名唯一，多个公开角色可以指向同一端口。允许接缝用两幅边界位置的无向候选对声明。复测只接通全局曼哈顿距离为 1 的候选对。栅格用行序列表示，每行列递增，像元是 0 至 100 的整数或 `None`。布尔值非法。

门槛 `t` 下，分数至少为 `t` 的已测像元活动。幅内按四邻接判连，幅间使用获准且同时活动的正对端口。站件表达各门槛的活动公开端口与幅内连通关系，内部像元坐标及逐点分数留站。中心将同层端口事实与接缝合并，再判断整幅通路。两探针同幅也可以出幅后返回。上限取 0 至 100 中仍连通的最大整数。恰达请求分数即通过，零分可通与全层不通分别记录。

## 样例与核对

`examples/scan.json` 的左幅首末行都是 7 分，中间行都是 1 分。两个探针位于左幅首列的首末行。右幅上下两行也是 7 分，初版中间行是 1、5、1，正对接缝允许上行跨入右幅、经 5 分通道再返回左幅。初版上限为 5，门槛 6 需补测。右幅中心勘误为 3 分后，新上限为 3，旧号仍领取原 5 分及旧父件。回归同时核对恰达上限、零分与缺测、对角与正接、离线重开、无效输入、提交回滚和重复初始化，并用原栅格全局洪泛独立核对站件复测结果。

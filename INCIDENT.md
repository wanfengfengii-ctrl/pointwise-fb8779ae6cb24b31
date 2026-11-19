# 停源复测误放行

`examples/scan.json` 中，`top` 和 `bottom` 都在左幅。两枚探针所在行均以7分到达接缝，左幅连接这两行的所有像元只有1分。初版右幅可用5分通道连接两行，再经接缝回到左幅。勘误只把右幅中心从5改为3，接缝端口读数保持原样。

夜班选用初版东西幅，在扫描工位关闭后发起6分复测。故障报告给出上限7和「放行」。应报上限5和「补测」，请求门槛为5时应通过。改选勘误右幅后，6分复测应报上限3和「补测」，门槛为3时应通过。复测室重开后，两个合法定稿仍应按各自原号领取原裁决及父件。

在项目根目录用原业务回归复现初版事故。

```sh
python3 -B -m unittest tests.test_review.ReviewTests.test_reentry
```

该回归的 `REENTRY_CEILING_AND_GATE` 断言核对初版报告的上限与放行判定。`tests.test_station.StationTests.test_revision_sensitive_evidence` 核对更正前后的固定站件，`tests.test_handover.HandoverTests.test_amend_and_reopen` 核对更正、停源和重开后的两个定稿。完整核验和演示入口见 README.md。

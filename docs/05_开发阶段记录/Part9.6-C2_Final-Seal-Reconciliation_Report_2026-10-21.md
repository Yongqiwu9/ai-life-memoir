# Part 9.6-C2 — Final Seal 证据对账与文档准备

## 1. 结论、范围与基线

- 日期：2026-10-21（Asia/Shanghai）。
- **EVIDENCE RECONCILIATION PASS WITH SCOPE LIMITS / FINAL SEAL DOCUMENTS PREPARED / DOCUMENT GIT PENDING**。
- 当前Session合成文字Backend接入的实施与约定验证已通过；封板文档尚未暂存、提交或推送，也没有封板文档自身的exact CI。不提前标记正式Final Seal CI Passed，不开始下一阶段。
- 实施提交：`273cb6b282b39b2e6b060984386f65a816ef0cc6`；`feat(dialogue): integrate synthetic session text runtime`；parent `c8824b3c2c1d7c9ae6d633461787431166cd7a07`。
- 49路径（实施36/文档13，新增32/修改17）与已批准候选的提交blob哈希逐项一致；三份混合文档只提交6个C2差异块，12个既有C3差异块排除。此前只读Pre-Commit Audit及Staged Audit通过；本轮不冒称新增独立实现总审。
- 完整字段、73项代码/测试关联、远程step/node、产物哈希及原报告哈希见[最终证据JSON](Part9.6-C2_Final-Seal-CI-Evidence_2026-10-21.json)。[原73项对账](Part9.6-C2_D01-D73_Acceptance-Reconciliation_2026-10-21.md)及初审/修复/失败历史保持原文，旧“待CI”是当时快照，由本报告补充结局。

## 2. exact commit远程CI

| 范围 | 实际远程结果 | 边界 |
| --- | --- | --- |
| Backend Fast | **778 PASS**，124 deselected，32 warnings | 候选提交实际执行，不含未提交C3/BM-01测试 |
| 普通PostgreSQL | **48 PASS**，778 deselected，11 warnings | 新head c296a4e8d102的实际回归，补足D61 |
| B PostgreSQL16.15 | **45 PASS，含竞争11**，无失败/跳过 | Manager/Runner分离；迁移及前后检查通过，cleanup verified |
| Dialogue PostgreSQL16.15 | **迁移4／运行27 PASS，含竞争16**，无失败/跳过 | 实际Linux job；fresh/current/check及清理通过，补足D70 |
| AI Service全合成套件 | **366 PASS**，1 warning | 含原C1与6项ASGI；本次为真实远程执行 |
| Ruff/format | PASS，181文件格式已符合 | 对应提交文件树；本地195包含排除文件，不要求远程凑数 |
| Alembic | 单head c296a4e8d102；fresh/current/check及集成后current/check PASS | 无新增upgrade operations |

[Backend CI 39567318542](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/39567318542)与[Dialogue CI 39567318350](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/39567318350)均为master/push，headSha exact `273cb6b...`，status=completed、conclusion=success。四个job全部成功，不能用旧C1 CI代替。

两专项manifest绑定同一提交，PG实际版本16.15，状态CLEANED，database_absent/roles_absent=true，cleanup=verified；B5项、Dialogue14项source_hashes与提交字节一致。JUnit节点精确计数，未跳过竞争测试。B9份/Dialogue10份进程回执与清理证据已归档；本地旧UNKNOWN资源没有被操作，也不据此宣称旧资源已清理。

推送后实时ls-remote已确认exact SHA，本轮GitHub API再次确认master仍指向该SHA；本轮Git HTTPS查询曾超时，未将超时说成成功。原推送授权及这份文档准备均不授权额外push。

## 3. 本地与远程计数对账

本地2026-10-21Backend1008新执行包括未提交C3/BM-01合成278，主线730＋复用2026-10-19 HTTP48覆盖778；新远程实际报告778。AI本地纯360＋复用ASGI6覆盖366，新远程实际报告366。它们是不同日期、不同环境的验证，不能相加或把复用改称本地新执行。

本地Python3.14.0，远程Python3.12.15。远程执行补足候选提交在项目CI Python3.12下的回归证据；不扩大到所有依赖组合。PG本地2026-10-20迁移4/运行27（竞争16）及HBA精确恢复历史保持；本轮只读取CI，不重新连接本地DB、Docker、HBA或运行迁移/测试。

## 4. D01–D73最终证据索引

下表是当前会话的证据对账，不是73项新测试或新增独立总审。“远程专项节点数”可重复支撑多个要求，不可相加为测试总数；Fast/AI/HTTP节点、代码路径及原执行证据详见JSON及原73项表。

| ID | 要求 | 本次对账 | 远程专项关联节点数 |
| --- | --- | --- | --- |
| D01 | 严格wire／类型／大小 | 约定范围证据已核对 | 0 |
| D02 | 绑定错配及跨scope拒绝 | 约定范围证据已核对 | 0 |
| D03 | 内部认证／默认配置关闭 | 约定范围证据已核对 | 0 |
| D04 | 纯transition不执行generator | 约定范围证据已核对 | 0 |
| D05 | 同一C1内核初始化／不可变transition | 约定范围证据已核对 | 0 |
| D06 | 内部错误脱敏 | 约定范围证据已核对 | 0 |
| D07 | Owner／Family／Session隔离 | 约定范围证据已核对 | 0 |
| D08 | 拒绝客户端伪造synthetic／Consent／Provider | 约定范围证据已核对 | 0 |
| D09 | 仅已分配Session可处理 | 约定范围证据已核对 | 0 |
| D10 | 旧v1/v2保留及旧写入口拒绝 | 约定范围证据已核对 | 1 |
| D11 | State完整字段分区／重建 | 约定范围证据已核对 | 0 |
| D12 | 缺失／孤儿／额外叶拒绝 | 约定范围证据已核对 | 0 |
| D13 | 依赖预检先于正文／敏感SELECT | 约定范围证据已核对 | 0 |
| D14 | 重启精确Context／label／历史交付状态 | 约定范围证据已核对 | 0 |
| D15 | 来源缺失／改变先于Provider拒绝 | 约定范围证据已核对 | 1 |
| D16 | 传递AI历史依赖受限 | 约定范围证据已核对 | 0 |
| D17 | 替换后清除退休叶／不复制Context正文 | 约定范围证据已核对 | 0 |
| D18 | 不读取敏感字段的blind purge | 约定范围证据已核对 | 0 |
| D19 | 损坏checkpoint下metadata GET | 约定范围证据已核对 | 0 |
| D20 | Message单版本来源投影／不伪造Artifact | 约定范围证据已核对 | 0 |
| D21 | 原文／binding／queued Turn原子提交 | 约定范围证据已核对 | 0 |
| D22 | 各输入写边界回滚 | 约定范围证据已核对 | 0 |
| D23 | 故障时已保存原文＋queued语义 | 约定范围证据已核对 | 0 |
| D24 | apply重放不重复原文 | 约定范围证据已核对 | 2 |
| D25 | 旧text／transcript入口不能绕过 | 约定范围证据已核对 | 0 |
| D26 | 父行锁／Message序号 | 约定范围证据已核对 | 1 |
| D27 | 同key并发只写一份Message／Turn | 约定范围证据已核对 | 1 |
| D28 | 载荷冲突／历史HMAC key轮换 | 约定范围证据已核对 | 0 |
| D29 | RPC前持久化stop fence | 约定范围证据已核对 | 2 |
| D30 | RPC故障pause与显式同步 | 约定范围证据已核对 | 2 |
| D31 | 暂停中原文仍可入队 | 约定范围证据已核对 | 0 |
| D32 | resume按序非生成同步 | 约定范围证据已核对 | 0 |
| D33 | 重复pause不恢复额度／不双推进 | 约定范围证据已核对 | 0 |
| D34 | blocked／无checkpoint下end无RPC及正文读 | 约定范围证据已核对 | 0 |
| D35 | end作废queued输入／控制／effect | 约定范围证据已核对 | 3 |
| D36 | record_only／typing屏障 | 约定范围证据已核对 | 3 |
| D37 | Session结束后拒绝新原文 | 约定范围证据已核对 | 0 |
| D38 | 逻辑时钟重启／回退／旧timer | 约定范围证据已核对 | 0 |
| D39 | UNKNOWN拒绝重调／new key | 约定范围证据已核对 | 1 |
| D40 | 普通旧version拒绝，安全停止例外 | 约定范围证据已核对 | 2 |
| D41 | 普通CAS竞争无丢更新 | 约定范围证据已核对 | 1 |
| D42 | stop对reserve／ready发布竞争 | 约定范围证据已核对 | 2 |
| D43 | 输入与delivery-start竞争 | 约定范围证据已核对 | 1 |
| D44 | effect claim后故障不能重调 | 约定范围证据已核对 | 1 |
| D45 | delivery提交不确定读回不重复 | 约定范围证据已核对 | 1 |
| D46 | prepare到publish间来源失效 | 约定范围证据已核对 | 4 |
| D47 | delivery token／scope／正文门禁 | 约定范围证据已核对 | 0 |
| D48 | 重放／迟到结果不复活 | 约定范围证据已核对 | 2 |
| D49 | 旧completion不能完成新response | 约定范围证据已核对 | 0 |
| D50 | ready／started／completed／interrupted区别 | 约定范围证据已核对 | 0 |
| D51 | DEBUG两模式各隐私边界 | 约定范围证据已核对 | 0 |
| D52 | 只读对账不写／不读正文／不调AI／不枚举 | 约定范围证据已核对 | 0 |
| D53 | fresh16.15及精确head/current/check | 约定范围证据已核对 | 1 |
| D54 | Legacy升级值与NULL兼容 | 约定范围证据已核对 | 1 |
| D55 | downgrade表／字段marker防护 | 批准静态证明＋本地/远程marker执行 | 1 |
| D56 | empty／Legacy回退与旧约束恢复 | 约定范围证据已核对 | 1 |
| D57 | 真实约束SQLSTATE与rollback | 约定范围证据已核对 | 1 |
| D58 | 默认expire与独立连接 | 约定范围证据已核对 | 8 |
| D59 | CI缺失／重复／skip／节点归属攻击 | 约定范围证据已核对 | 0 |
| D60 | Manager／Runner权限及UNKNOWN停止清理 | 本次范围证据确认；历史UNKNOWN限制保留 | 1 |
| D61 | C1＋Backend Fast＋普通PG完整回归 | 远程完整回归执行门禁满足 | 0 |
| D62 | 默认关闭／无真实Provider或Consent绕过 | 约定范围证据已核对 | 0 |
| D63 | 既有工作区／暂存区保护 | 约定范围证据已核对 | 0 |
| D64 | 如实区分scope／UNKNOWN／生产限制 | 约定范围证据已核对 | 0 |
| D65 | 无新输入连续提问／刷新恢复及碰撞 | 约定范围证据已核对 | 5 |
| D66 | 实际变化才刷新／两revision精确推进 | 约定范围证据已核对 | 5 |
| D67 | stop-first旧ready／timeout不污染G2 | 约定范围证据已核对 | 2 |
| D68 | unknown-first阻塞且安全stop不能清除 | 约定范围证据已核对 | 1 |
| D69 | idle／initializing安全与非法事件 | 约定范围证据已核对 | 0 |
| D70 | 新head父链／B与Dialogue远程job | exact B/Dialogue及清理门禁满足 | 0 |
| D71 | 完整checkpoint HMAC／受限先拒绝 | 约定范围证据已核对 | 0 |
| D72 | 冻结attempt重放／保存来源pause恢复 | 约定范围证据已核对 | 7 |
| D73 | 真实PG父子协调全边界／抢占／迟到 | 约定范围证据已核对 | 11 |

### 执行门禁与特殊证明

- **D61 EXECUTION GATE SATISFIED**：exact提交Fast778、普通PG48、AI366均实际通过；无须为这份文档再分配本地PG或重复HTTP。
- **D70 EXECUTION GATE SATISFIED**：exact提交B45/竞争11与Dialogue迁移4/运行27/竞争16、精确head及verified cleanup均有实际证据。
- **D55**继续采用已批准的marker实际执行＋静态约束证明；五张新表及State10/Turn15新增字段防护、排他锁先于拒绝检查、DDL在后。指针/新版引用由表非空防护涵盖；孤儿仅属约束被绕过/损坏边界，不制造非法fixture。
- **D60**确认受限Runner与本轮Manager清理门禁；SUP-IR-01只关闭新增P03两处Session生命周期。历史同型UNKNOWN路径及旧UNKNOWN资源范围保留，不以CI成功隐式关闭。
- **D65/D72/D73**真实PG上已知提交边界的合成故障、独立Session读回及竞争证据有效；不是任意kill/真实driver断连/第三方收费不确定结果验证。
- 原合同独立审查、定向修复与复审结论按各自范围保留。本报告未新增独立实现审查，也不把作者对账冒充原审查人的新签字。

## 5. 封板准备与保留限制

约定实现范围内未发现新增待补执行证据；后续门禁为本次五份文档的只读审计、精确hunk暂存审计，以及分别批准的文档commit/push和exact CI。当前仅为Final Seal准备，不声称文档Git闭环已完成，不启动下一功能阶段。

真实Provider/费用能力、真实语音/STT/TTS、真实个人资料、日记/笔记真实存储与资料集、多来源、C3激活/C4/C6、第三方/备份删除及生产继续关闭；旧UNKNOWN/BM-01及历史审查范围不扩大。**DEVELOPMENT SNAPSHOT ONLY / NOT PRODUCTION READY**。

## 6. 本轮安全边界

仅新增本报告和证据JSON，同步README/路线图/开发日志；原C2合同、初审/复审、失败、17/13、27/16、本地差集及73项报告字节保持。运行时代码、测试、Migration、workflow、AGENTS及C3/BM-01不改；不读ad或环境密钥，不运行测试/数据库/Docker/迁移，不做Git写操作。暂存区空，16历史删除unstaged、ad untracked、.env.test ignored。

三份入口文档仍带既有C3差异；未来只能选本轮C2封板差异，不能整文件加入。封板文档自身尚无commit或远程CI；本报告中的success始终绑定实施提交273cb6b。

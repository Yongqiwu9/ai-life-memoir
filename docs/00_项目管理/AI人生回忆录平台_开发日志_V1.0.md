# AI人生回忆录平台_开发日志_V1.0

## 2026-10-21 — 9.6-C2最新差集回归与D01–D73总对账（当前）

- 用户要求推进最新完整回归、D01–D73总对账、远程CI和Git闭环。按此前不重复专项HTTP的边界，执行前声明复用代码未变化的C2 HTTP48／AI ASGI6，其余全部Backend顶层Fast及AI纯离线文件新执行；普通API回归仍属于本次Fast，不另跑专项HTTP或PG。
- 实际新执行：**Backend1008 PASS／AI Service纯离线360 PASS**，无失败/错误/跳过。本地Python3.14.0；Backend退出0、线程0、275个固定纯C1/SQLite/import子进程退出及通信确认，retained=false。仅外部任务目录写证据，未修改项目源码或激活真实C3/BM-01 provisioning。
- Ruff/format：Backend195／AI30文件通过；B43／Dialogue47纯mock自检通过；脚本Alembic heads为c296a4e8d102单一head，无DB连接。保留32条警告：Starlette/httpx弃用1、Memory测试fixture循环表排序31；不为消警告顺便改实现。
- [73项验收总对账](../05_开发阶段记录/Part9.6-C2_D01-D73_Acceptance-Reconciliation_2026-10-21.md)与[回归验收证据](../05_开发阶段记录/Part9.6-C2_Full-Regression-Acceptance-Evidence_2026-10-21.json)逐项记录代码、测试和实际执行/静态证明；尚待新增独立总审，不标73项全部PASS。D55依批准边界采用静态防护证明＋既有实际marker拒绝；D60保留历史同型UNKNOWN范围，不由新增P03关闭推定全历史已整改。
- 提交范围拆分：本地1008项中C3/BM-01合成278项不提交（18＋128＋132）；拟提交主线新执行730＋复用C2 HTTP48覆盖778项，不冒称远程已报778。当前49路径候选（实施36／文档13），三份混合文档仅选6个C2差异块，12个既有C3差异块排除；外部patch只读检查通过，尚未暂存。
- 复用已清理的PG16.15新run651797b3（迁移4／运行27／其中竞争16）及历史HTTP48/6。1008＋48、360＋6为分日期证据覆盖，不是此次单次Fast1056/AI366新执行；也不拿旧65＋2冒充最新全量。
- **D61普通PG在新head的完整回归、D70未来exact C2 commit的B/Dialogue等远程job仍待执行**。未创建新commit或触发远程CI，C1 seal c882旧CI不替代。下一步为精确候选及混合文档hunk审计，再分别批准暂存、commit、push，按exact SHA等待CI；暂不封板。
- 项目既有代码、测试、workflow、Migration、AGENTS及C3/BM-01保持；原报告/失败/复审不回填。暂存区空、16历史删除unstaged、ad未读/untracked、.env.test未读/ignored。本轮无Git写操作，不操作真实PG/Docker/迁移或旧UNKNOWN资源；真实Provider/语音/个人资料、资料集、多来源、C4/C6及生产限制保留。

## 2026-10-20 — 9.6-C2最小补验、SUP-IR-01关闭及新PG证据收尾（历史快照）

- 用户批准的最小补验V1.1限定三个项目文件及现有外部PG脚本；S01–S09离线补验，P01五恢复边界、P02两来源恢复、P03三真实竞争。原17项运行/13项竞争保留，固定清单更新为27项/其中16竞争/迁移4，未改业务、迁移或通用平台。
- 离线主回归65、末轮差集2 PASS，去重66节点；CI脚本Backend工作目录47项mock自检及Ruff/format通过。原首轮造数失败、旧静默假设失败仍保留；不将65＋2改记为PG生命周期修复后的重跑，不声称最新完整Fast/AI Service已通过。
- 独立实现复审初判FAIL：SUP-IR-01 Medium指向新增P03两个Session未强引用登记且UNKNOWN时自动close，是测试资源管理问题，不据此认定业务权限漏洞。用户批准仅修复两处：登记至guard.resources，先guard.check再close，UNKNOWN保留，不使用会误判存活线程的finish。原审查人定向静态复审PASS/CLOSED；PG文件新SHA256为6126c6929e4850122830d8f7afefcb58f3f8493099a43bc20d476aa31c1e0ec6，旧FAIL和修复前哈希保留。
- 随后获专项执行/HBA授权，新run `651797b3-a319-44d9-ac7a-5bef75d88b83` 在PG16.15实际完成**迁移4／运行27（含竞争16）PASS**，零跳过；fresh upgrade、前后current/check通过。Manager与受限Runner分离，34份回执、56个控制进程退出及EOF确认，库/角色名称及OID/会话/本次HBA规则清理核验通过，HBA原文哈希一致。旧UNKNOWN未触碰，无FORCE/任意kill或容器生命周期操作。
- 运行时361项输入锁匹配；执行前仅按审查哈希更新四份补验文件与三份先前入口文档，旧锁和七条差异有审计。本轮文档同步不回写该历史执行快照。
- 本轮Documentation Only新增[补验对账](../05_开发阶段记录/Part9.6-C2_Minimal-Supplement-Reconciliation_Report_2026-10-20.md)及[脱敏证据JSON](../05_开发阶段记录/Part9.6-C2_Minimal-Supplement-Evidence_2026-10-20.json)，同步README/路线图/本日志。前次17／13报告、合同、失败与审查历史均保留原文；历史HTTP48/6不重复执行。
- 状态：**LOCAL MINIMAL SUPPLEMENT PASS / CLEANUP CONFIRMED / NOT SEALED**。最新完整回归、D01–D73总对账、exact新C2远程CI及Git闭环仍待完成。真实Provider/语音/个人资料、资料集、多来源、C3激活/C4/C6、生产、BM-01及旧UNKNOWN限制不变。
- 本文档任务未运行测试、HTTP、PG、Docker或迁移，未改源码、配置或Git；16历史删除仍unstaged、ad untracked且未读、.env.test ignored且未读，AGENTS及C3/BM-01既有内容保持。暂存、提交、推送仍须分别授权，暂不封板。

## 2026-10-20 — 9.6-C2单用例复审、PG专项通过与文档收尾（前次专项历史）

- 用户授权：复审当前单用例修正→隔离PG专项→证据对账与文档收尾；不扩建启动平台，不重复HTTP，不授权Git写入或封板。
- `test_parent_lock_sequence` 独立只读定向复审PASS；固定PID与事务连接，核验holder阻塞者，线程结果/脱敏异常回传及有界join/UNKNOWN保留。5/3/10秒与成功写入/消息序号断言保持；Ruff/format PASS。
- 新唯一临时库PG16.15迁移4、运行17（其中竞争13）全部PASS，零失败/错误/跳过；fresh upgrade、前后current/check PASS，精确head c296a4e8d102。Manager和受限Runner分离，运行后清理核验库/角色/会话均不存在，HBA逐字节恢复。
- 沿用2026-10-19 Backend合成HTTP48／AI Service ASGI6 PASS，本轮未重跑HTTP或全量Fast/AI Service。旧失败/诊断报告保留，不回填历史通过，不触碰旧UNKNOWN。
- 新增[专项对账报告](../05_开发阶段记录/Part9.6-C2_Specialist-Validation-Reconciliation_Report_2026-10-20.md)与[脱敏证据JSON](../05_开发阶段记录/Part9.6-C2_Specialist-Validation-Evidence_2026-10-20.json)，同步README/路线图/本日志。本轮未额外修改业务、迁移、workflow或AGENTS；保留C3/BM-01和既有工作区内容、16历史删除、ad与ignored .env.test。无暂存/提交/推送。
- 状态：**本地专项证据闭环，C2 NOT SEALED；完整D01–D73封板对账、exact C2远程CI和Git闭环待完成**。真实语音/Provider/个人资料、资料集、多来源、C3激活/C4/C6、生产及旧UNKNOWN/BM-01限制不变。
- 下一门禁：本轮修正及文档差集审查、完整合同证据对账与精确候选审计。不得由本次专项PASS直接宣布整个C2完成或开始下一功能阶段。

## 2026-10-16 — Session合成文字接入合同及独立审查归档（历史快照）

- 用户确认下一工作包范围A：当前Session合成文字接入，暂名9.6-C2。本次只归档合同与审查，不批准实施。
- 状态：**合同独立静态审查及定向修订闭环PASS；V0.4及35路径实施待用户批准，Implementation NOT STARTED**。验收D01–D73全部NOT RUN。
- 补齐Checkpoint逐字段保存/重建/敏感隔离、Backend停止fence与故障同步、原文+durable事件事务、父子命令协调及完整约束/迁移/CI范围。原B CI精确head与B fixture维护纳入35路径，B45/竞争11和Manager/Runner门禁不放宽。
- 独立初审确认6项问题，V0.3发现父/子同时preparing直接回归，最终V0.4均在定向静态范围关闭，共7项。三位审查人只读核对合同及实际源码，未运行测试/HTTP/PG/Docker/网络，旧FAIL和各版hash历史保留。
- [V0.4合同](../04_AI设计/Part9.6-C2_Session-Text-Integration_Implementation-Contract_Draft_V0.4.md)原始字节保真，SHA256 `6589c552f896e40f47a789a7fdae63f2bc91ef18485ae04e75c6aa462918a68c`；[独立审查](../05_开发阶段记录/Part9.6-C2_Independent-Contract-Review_Report_2026-10-16.md)仅整理归档metadata和内部链接；[审查元数据](../05_开发阶段记录/Part9.6-C2_Contract-Review-Evidence_2026-10-16.json)记录review范围/关闭/候选清单。
- 前阶段C1封板文档commit `c8824b3c2c1d7c9ae6d633461787431166cd7a07`已推送，exact [Backend CI38863558414](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/38863558414) completed/success。Backend CI不包含AI Service C1；本地20/203/350是既有记录，本轮未重跑。下方旧“文档Git待完成”仍为当时快照。
- 真实Provider/语音/个人资料、资料集、多来源、C4/C6、生产、旧UNKNOWN及BM-01限制继续保留。未改runtime/tests/workflow/Migration/配置/数据库，未运行验证或Git写操作；AGENTS、C3/BM-01、16历史删除、ad及ignored .env.test保持，混合文档按hunk排除。
- 下一门禁为实施批准；文档暂存/提交/推送、HTTP/ASGI及隔离PG16.15执行仍须对应专项授权。

## 2026-10-16 — 9.6-C1最终对账通过与Final Seal文档准备（历史快照）

- 状态：**合成离线验收闭环通过；Final Seal文档已准备，文档Git闭环待完成**。实施提交`6825be4e01345b1992b08f90f864a54fc0fef7e3`已普通推送；exact [Backend CI 38796788780](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/38796788780) completed/success。推送时本地/实时远端一致，0/0。
- 本次只读对账确认C01–C58完整、11文件工作区/提交/最终验收哈希一致，原始XML哈希和完整节点集合一致。三项修复及C52/C54已有定向静态关闭意见；未发现阻塞C1合成离线封板的证据缺口，不重复测试。
- 本地既有证据20／203／350 PASS，零失败/错误/跳过，Ruff/format PASS；独立审查人未独立执行。远程Fast642／普通PG48、Alembic和B专项PG16.15 job通过。当前workflow未运行AI Service/C1，不混称远程350通过，也不据此关闭C1 Backend/数据库接入限制。
- 本轮Documentation Only新增[封板对账](../05_开发阶段记录/Part9.6-C1_Final-Seal-Reconciliation_Report_2026-10-16.md)与[CI证据](../05_开发阶段记录/Part9.6-C1_Final-Seal-CI-Evidence_2026-10-16.json)，同步三个项目入口并审计；原合同、实施/初审/复审和本地验收元数据保持原文。下方旧未提交/无CI状态保留当时历史，不覆盖本条。
- 真实语音/STT/TTS、Provider/费用能力、Backend/HTTP接入、C1数据库、C4/C6、真实个人资料、生产及旧UNKNOWN继续保留；BM-01不关闭，后续工作包未启动。
- 未修改代码、测试、workflow、Migration、配置或数据库，未运行测试/HTTP/PG/Docker/Provider。本轮未暂存、提交或推送；文档exact commit及CI尚不存在，后续Git步骤分别批准。AGENTS、C3/BM-01、16历史删除、ad及ignored .env.test保持；三份混合入口仅允许本轮hunks进入后续候选。

## 2026-10-16 — 9.6-C1实施、独立初审与定向复审结果归档（历史快照）

- 当前状态：**合成离线实施及定向复审通过，Git 闭环待完成**。基线master @ 3873c744eec87af2740731d1098cbd488d145ef2；用户批准的11文件合成离线实施已完成，未暂存、未提交、未推送、未封板，尚无该源码对应的远程CI。
- 修复前实施记录：C1 183／AI Service全量330 passed，其中既有147；内部自查不替代正式独立实现审查。后续正式独立初审FAIL：三项P2为受限来源的AI历史依赖未覆盖、availability缺项默认可用、Unicode规范化可令合法交付异常；另有C52已消耗额度、C54新输出正在交付的验收缺口。原合同审查PASS及实现初审FAIL均保留，不改写旧结论。
- 用户批准限定修复后，仅修改原11文件内的5份。元数据预检先于正文摘要/生成/交付，AI祖先依赖随新请求传递，不增加可读正文；availability必填；规范化容量在deliver前受控校验，不截断去重内容。补齐C52与C54实质断言。
- 最新实际本地执行：修复专项20／C1 203／AI Service全量350（203＋既有147）passed，均0failed/0errors/0skipped，Ruff/format PASS。原审查人定向静态复审PASS，三项问题和两项验收缺口CLOSED；审查人只读核对源码与执行元数据，未独立运行测试。
- 保留真实语音/STT/TTS、真实Provider/费用门禁、Backend/HTTP接入、数据库、真实个人资料、C4/C6、备份/第三方删除、生产及旧UNKNOWN限制。不关闭BM-01，不把C1内核写成真实日记存储、多来源Memory或语音产品完成。B封板及其PG/CI证据不被本轮本地AI Service数量替代。
- 本轮Documentation Only归档实施、初审、修复/定向复审与验收元数据，必要同步README/路线图/本日志，随后只读Pre-Commit Audit。未改源码、测试、workflow、Migration、配置或数据库，未重跑测试、HTTP、PG、Docker或Provider。AGENTS、C3/BM-01、16历史删除、ad、ignored .env.test保持；三份入口文档的既有C3 hunks须排除，不能整文件暂存。
- 详细记录：[实施历史](../05_开发阶段记录/Part9.6-C1_Implementation-and-Validation_Report_2026-10-16.md)、[独立初审FAIL](../05_开发阶段记录/Part9.6-C1_Independent-Implementation-Review_Report_2026-10-16.md)、[修复及定向复审PASS](../05_开发阶段记录/Part9.6-C1_Remediation-and-Targeted-Review_Report_2026-10-16.md)、[执行元数据与源码哈希](../05_开发阶段记录/Part9.6-C1_Validation-Evidence_2026-10-16.json)。后续暂存、提交、推送分别等待用户批准。

## 2026-10-15 — 9.6-B最终封板确认与9.6-C/C1合同、审查报告归档（历史快照）

- 用户批准的B封板文档提交0e39a39b22a72be361833dd0ae42c40f80146b1e已普通推送；exact Backend CI38691707005 completed/success，Fast642／普通PG48／B专项45（其中竞争11、0skip），Ruff/format、Alembic及清理verified。本轮仅引用既有证据，不重跑；用户随后最终确认B Completed / Sealed（约定范围）。
- 新产品方向已确认：语音/文字连续回忆、独立输入日记笔记；默认轻陪伴、同段静默最多回应一次、用户开口停播；资料显式选具体版本/资料集，新增/改版不自动入当前任务。原始来源不覆盖，AI内容不冒充讲述者事实，仍走精确Revision人工审批。
- 完整产品路线及C1合成离线决策内核工程合同已完成两项独立静态审查。初审4项Medium合同问题经修订复审CLOSED：轮次/静默字段、回调与版本、播放/去重关联、来源Scope。旧turn迟到提交不改当前hint/静默额度；受限来源不能用旧Context再次生成。
- 仅归档批准候选：C1精确11新增文件、58项未来验收；Implementation Not Started，无代码/Migration/API接入或真实语音/笔记存储。全产品后续工作包未冻结；不因静态审查通过认定已实现或授权实施。
- Provider/模型、预算数值/币种/价格/能力未确认。真实个人资料、C4/C6、来源持久化、多来源B兼容、备份/第三方、生产和旧UNKNOWN保持；AI58/Legacy18为历史执行。B38/B46/B48及BM-01边界不变。
- 本轮Documentation Only：合同原始UTF-8字节保真（SHA256 F036874A1C8A3401C73A375BC2E833BD745FCAAEBD0F97FADBEA329C06A18563）；报告仅加归档metadata与修正内部链接，保留初审FAIL和各轮意见历史。README/路线图/本日志仅必要同步。
- 未修改runtime/tests/workflow/Migration/数据库，未运行测试/应用/Provider，未暂存/提交/推送。AGENTS、C3/BM-01、16历史删除、ad、ignored .env.test保持；三入口文档原12个C3 hunks保留并排除候选。
- 详细SSOT：[合同](../04_AI设计/Part9.6-C_Continuous-Reminiscence_Engineering-Contract_Draft_V1.0.md)与[独立审查报告](../05_开发阶段记录/Part9.6-C1_Independent-Contract-Review_Report_2026-10-15.md)。下一步为Documentation Only归档复核；实施、暂存、提交、推送须分别授权。此前“封板准备/未归档”记录对应当时状态，不回写原报告。

## 2026-10-15 — 9.6-B 实现CI闭环、E-01定向关闭意见归档与封板文档准备（当时快照）

- 基线e164c521e2ac5ed5aba992a327ae8e34b94bf00f（test(memory): close six-item validation gaps）已普通推送；exact-commit Backend CI38617553685双job completed/success，HEAD与origin/master一致（推送核验时0/0）。
- 真实远程Fast642／93 deselected、普通PG48／642 deselected；B专项PostgreSQL16.15完整45项、竞争11、0skip。JUnit节点、manifest源码hash与该commit一致，非旧35加本地10。fresh b196、前后current/check、受限Runner及Manager精确清理verified，进程exit0/EOF，私有载体已清除。
- B01–B57正式归档：54行约定层执行、B38确认边界、B46静态inventory、B48旧执行＋约束证明。原审查人E-01定向复核PASS；B32/B33/B52竞争、57条对账、Legacy计数歧义及降级分支B范围证据缺口CLOSED；真实能力与历史状态限制拆分保留，旧初审原文不改写。
- B38同旧Memory恢复正例后置C4；B46不证明实际删除传播；B48不禁FK造孤儿、不声称UNION每谓词独立命中。历史AI58和Legacy18未在最新Backend CI重跑；本地Fast920含未提交C3，仅对应其历史工作区。
- 真实Provider、生产Consent/C4/C6、备份/第三方清除和生产回退/部署仍未完成；默认真实处理关闭，旧v3 UNKNOWN保留，不宣称Production Ready或BM-01 CLOSED。上一轮开发库检查结果不纳入本次E-01复核或封板证据。
- 当前为Implementation Completed / Validation Passed（约定范围），Final Documentation Seal Preparation。封板文档未提交/推送，尚无文档提交对应CI；未正式封板，不开始下一阶段。
- 本轮Documentation Only：归档对账Markdown/JSON与E-01独立回传原文，同步README/路线图/日志；不改代码、测试、workflow、migration或数据库，不重跑验证，不暂存/提交/推送。既有C3/BM-01、AGENTS、16项历史删除、ad、ignored .env.test保持。
- 后续门禁：交「Git Commit Review」只读文档审计；通过后再分别批准暂存/提交/推送，并待文档exact-commit CI通过后确认正式封板。详见[57项对账](../05_开发阶段记录/Part9.6-B_B01-B57_Acceptance-Reconciliation_2026-10-15.md)与[E-01独立意见](../05_开发阶段记录/Part9.6-B_E01_Coverage-Closure_Independent-Review_2026-10-15.md)。

## 2026-10-14 — 六项补验差集完成与独立复核（提交前历史）

- 基线c25c3f85ea9f3c379001653a5109c523faa20162已推送，exact-commit Backend CI38554717815双job成功，B35／竞争11通过；下方此前“未提交/未推送”保留历史时点，不覆盖本节。
- 用户批准五文件44新增实例，新增合成34 passed（Service15/实际ASGI19）、完整工作区Fast920 passed/130 deselected/215.53s；含未提交C3，非远程数量。Ruff/format与43项CI mock自检通过，AI Service58仅沿用旧证据未重跑。
- 真实PG16.15/160015仅新增B34十项：10 passed/35 deselected/7.71s/0skip，逐项实际SQLSTATE与有限约束集合匹配；fresh b196及前后current/check通过。run b11b1369-3894-4b25-90dc-a9135ad1e1d2，库/两角色/会话不存在、HBA恢复、历史OID/ACL和310源码哈希不变；锁进程exit0、线程0。首轮选择gate零测试启动失败清理后，仅修临时入口并全新分配通过，项目未因启动器整改而变化。
- 「9.6-A Review」合同定向复审、五文件实现复审、PG及清理证据复核均PASS；B18/34/47/49/54/57按相应层级关闭，B54两码为模拟diagnostic，非真实引擎双码证明。
- B38同旧Memory恢复正例后置C4；B48已有18场景＋静态约束证明收敛。新CI45／竞争11尚无对应远程执行；未封板，不自动关闭E-01或宣称全57项全层验证。真实Provider/C4/C6/生产边界和旧UNKNOWN保留。
- 本次仅同步文档，五源码和migration/runtime/workflow未再修改，未运行测试/PG/Docker，未暂存/提交/推送；下一步「Git Commit Review」只读Pre-Commit Audit，混合文档按hunk排除C3/BM-01。
- 结果及原始证据：[六项补验结果](../05_开发阶段记录/Part9.6-B_Six-Item-Validation-Delta_Report_2026-10-14.md)。

## 2026-10-14 — 9.6-B 补验完成与 SUP-IR-01 关闭（此前历史快照）

- 当前 Git 基线 `0099016455f21cd32bed3bbe1c3d24a313ab140d`；补验源码与本次文档同步尚未提交。本节更新此前“最新”记录，旧条目按各自执行时点保留。
- 完整工作区 Fast **886 passed / 120 deselected / 179.28s**；包含新增 109 项离线用例（其中 HTTP/ASGI 23 项）。AI Service **58 passed / 0.56s**，未连接真实模型。工作区含既有未提交内容，不等于远程基线的测试数量。
- 真实 PostgreSQL **16.15 / 160015**：**35 passed / 3.69s，11 项竞争测试全部通过，0 skipped**；旧 28 项加新增 7 项。Provider 锁释放探针另列，B32/B33/B52 指定竞争证据已补齐。Manager fresh upgrade 到 `b196f0d47a21`、测试前后 current/check 均 PASS。
- PG run `074c4869-3c51-4e91-8b10-c33ec4922db7`：使用现有容器中唯一新库与独立 owner/受限 Runner；进程/线程确认退出；库、两角色、相关会话已核验不存在，HBA 原始哈希恢复、规则错误 0，历史库/角色元数据不变，临时凭据载体已删除。308 个既有受保护文件和 Git 状态未变，旧 v3 UNKNOWN 不被替代。
- 「9.6-A Review」五文件只读独立复审 PASS WITH FINDINGS，无阻塞 PG 问题。唯一新增 Low SUP-IR-01 随后仅收紧终态重放断言为 failed503/discarded409/cancelled200；**3 passed / 0.55s**、Ruff/format 通过，定向复审 PASS / CLOSED。886/58 是这次断言修复前快照，修复后未重跑完整 Fast 或 PG。
- 已有 exact commit `0099016...` 的远程双 job 成功满足 B-PC-01 原接线关闭条件；旧远程 B 为 28／5，本地新增 35／11 尚未推送/远程验证。E-01 仅补齐指定差集，不整体关闭；57 项完整对账和未单独覆盖回退分支限制仍在。
- 本轮为 Documentation Only，未运行测试/数据库/Docker，未改代码/迁移/workflow，未暂存/提交/推送；16 项历史删除、`ad`、ignored `.env.test` 及 C3/BM-01 既有修改保留。真实 Provider、C4/C6、生产部署均不因通过而完成，保持 NOT PRODUCTION READY。
- 详细汇总及原始证据索引：[补充验收记录](../05_开发阶段记录/Part9.6-B_Supplemental-Validation_Report_2026-10-14.md)。下一步仅为只读 Pre-Commit Audit；不直接封板，Git 各步骤另获批准。

## 2026-10-14 — B CI定向复审通过（补验前历史）

- 「9.6-A Review」仅对CI-IR-01～04定向只读复审，结论PASS；四项CLOSED — STATIC，6文件初末hash匹配。未运行脚本/DB/CI，不将模拟阶段/退出证据当成真实权限或清理成功。
- 实施者验证43项纯mock合同/故障注入检查、script Ruff/format、workflow YAML/接线均PASS；本机激活在资源前拒绝，未做本机Docker/PG操作。42个业务实施文件未变化。
- 新job实际Linux/PostgreSQL/Remote CI仍NOT RUN，B-PC-01继续OPEN直至exact-commit backend+B双job通过；E-01、旧v3 UNKNOWN保持。
- 未暂存、提交、推送。下一步对原50路径与新增workflow/专项脚本/CI合同的53路径候选union重新做定向Pre-Commit Audit，不直接复用旧50路径结论；README/路线图/日志仍有须排除的既有C3 hunks。

## 2026-10-14 — B CI 初审后定向修复

- 独立实现初审FAIL：CI-IR-01～03 Blocking Medium；CI-IR-04 Low。修复在既有六文件批准范围内，未改业务/测试/migration/AGENTS/BM-01，也未执行本机真实Docker/PG。
- 从Popen启动尝试前即禁止清理，持续保留原对象，cleanup检查所有已启动进程结局；未确认退出/EOF/group时保留。
- 权限准备连接的SQL异常统一进入不确定结果保留；阶段使用共享单调截止，将剩余预算传入native wait/connect/server SQL timeout，过期拒绝后续操作。
- post-check失败保留已通过test_result，单独记录post_check_result；overall仍失败。
- 43项纯mock合同/故障注入检查PASS；待独立定向再审，不先关闭finding。真实Linux/PG/Remote CI未运行，B-PC-01与E-01仍OPEN；未暂存、提交或推送。

## 2026-10-14 — B-PC-01 专项CI接线实施

- 用户批准独立合同审查及通过后的六文件实施；「9.6-A Review」合同审查PASS WITH FINDINGS。三项澄清：SQLSTATE缺失不补造、post-check使用受限Runner、数据库操作前核验专属job/service/端口/集群。
- 实施限workflow、单一专项CI脚本及本合同/README/路线图/日志。原integration精确排除B文件；独立16.15 job负责分配、迁移、受限Runner的28项（含5并发）、post-check、退出核验及精确清理；只上传脱敏manifest/summary/JUnit。
- 32项纯mock合同检查PASS；脚本Ruff/format PASS；workflow YAML与接线断言PASS；本机--ci-manager预检拒绝，未触发Docker/PG。以上不替代新job实际SQL权限、清理与GitHub验收。
- 状态：IMPLEMENTED LOCALLY / IMPLEMENTATION REVIEW PENDING / REMOTE CI NOT RUN；B-PC-01 REMEDIATION IMPLEMENTED但仍OPEN，E-01保持。业务源码、现有测试门禁和迁移未改，未扩建通用BM-01平台。
- 暂存区保持为空；未commit/push。详细设计和门禁只保存于[CI接线合同](../05_开发阶段记录/Part9.6-B_PostgreSQL-CI-Wiring_Implementation-Contract_V1.0.md)。独立实现复审通过后重新核对提交union和三份混合文档的精确hunks，不因旧50路径已审计就自动认可新增CI内容。

## 2026-10-14 — 9.6-B 验证闭环状态（补验前历史）

- 已批准的42文件离线实施写入工作区，未提交；B-IR-01～04 经「9.6-A Review」独立复核 CLOSED。
- 独立复核：**PASS WITH FINDINGS**；详细记录见 [闭环独立复核报告](../05_开发阶段记录/Part9.6-B_Validation-Closure_Independent-Review_2026-10-14.md)。
- HTTP/ASGI：现有合成用例 **15 passed / 3.67s**，每例独立内存SQLite；不证明生产JWT、真实Consent或真实Provider流程。
- PostgreSQL16.15：现有专项 **28 passed / 2.68s**，fresh upgrade与前后current/check通过；含5个真实双连接用例。
- Legacy/downgrade：**18个脚本验收场景**通过，不是18个pytest用例；原ID、正文、FK和时间保留，新增authority不补造；空库/纯Legacy可安全回退，测试的不安全回退被拒绝且schema/row快照不变。
- 本次成功及失败隔离run的临时库与角色均已核验清理，原HBA恢复；旧v3仍UNKNOWN，与本次资源分开。
- **E-01 Medium（证据限制，非已确认业务缺陷）**：57项不能由测试数量相加推断全部完成。B32既有Memory两提案竞争、B33 ordinal并发、B52预检后新增引用的指定真实PG场景仍未验证；真实Legacy孤儿、版本化Section等回退分支未单独覆盖。
- 真实Provider、完整生产Consent/C3/C5/C6、备份与第三方清除仍未实现/验证；不关闭BM-01，不标Production Ready或整个9.6-B Sealed。
- 下一门禁：**Git Commit Review 的只读 Pre-Commit Audit**；精确白名单与差异审计后仍需用户分别批准暂存、提交、推送。暂存区为空，16个历史删除/AGENTS/C3/BM-01/ad/.env.test均不得意外纳入。


> 最新主线状态（2026-10-12）：9.6-A Provider Extension 已本地提交 master @ `6c12e96e4f83ada7cb7c7dd60fec4283269f8700`，本次未核验 push/远端 CI。9.6-B Candidate + Immutable Revision + Human Review 完整草案已归档，产品决定 CONFIRMED，正式独立合同审查 PASS WITH FINDINGS，工程条款已修订 PENDING TARGETED RE-REVIEW，IMPLEMENTATION NOT STARTED / NOT AUTHORIZED；下一门禁为定向再审及实施批准。HTTP/ASGI NOT RUN、PostgreSQL NOT VERIFIED，DEVELOPMENT SNAPSHOT ONLY。前文保留历史阶段记录。

## 1. 项目简介

AI人生回忆录平台用于长期采集个人经历，通过家庭关系、访谈、录音、语音识别、AI分析，最终生成结构化人生回忆录。

核心链路：

User → Family → FamilyMember → Interview → InterviewSession →
AudioRecording → Transcript → TranscriptSegment → InterviewMessage → AI
Extraction → Memory → Memoir

------------------------------------------------------------------------

## 2. 开发阶段记录

### Part 9.1 Backend基础设施

完成：

-   Backend工程结构
-   FastAPI基础架构
-   数据库基础
-   Alembic迁移体系

### Part 9.2 Authentication / User

完成：

-   用户模型
-   JWT认证体系
-   用户安全边界

### Part 9.3 Family + FamilyMember

提交：

668d1e0 feat: implement family and family member

完成：

-   Family
-   FamilyMember
-   CRUD
-   Service
-   API
-   Owner Isolation

### Part 9.4 Interview

提交：

79bb296 feat: implement interview module

完成：

-   Interview
-   InterviewSession
-   InterviewMessage

已建立的数据关系：

User → Family → FamilyMember → Interview → InterviewSession → InterviewMessage

### Part 9.5 Audio/STT

提交：

e30f043 feat: implement audio and stt data infrastructure

完成：

-   AudioRecording
-   Transcript
-   TranscriptSegment

已建立的数据关系：

AudioRecording → Transcript → TranscriptSegment → InterviewMessage

说明：这是 Audio/STT 元数据与来源关系，不代表已实现 Audio upload、真实 STT Provider 或自动转写 Pipeline。

### Part 9.5.5-A Memory 前置产品决策与 ADR 冻结

提交：

616e478 docs: freeze pre-memory architecture decisions

完成：

-   产品约束与 ADR-001～ADR-009 状态整理
-   Family Archive 删除、协作、讲述者、Consent、状态机、Candidate 与第三方处理边界记录

### Part 9.5.5-B PostgreSQL Integration Test + CI Baseline

状态：

Completed，2026-10-05 本地 PostgreSQL 与真实远程 GitHub Actions 验证均通过。

已实现：

-   保留 SQLite 快速测试
-   独立 PostgreSQL integration marker、Alembic/pytest 共用的 `TEST_DATABASE_URL` 加载与测试库名称安全检查
-   本地从 Git 忽略的 `apps/backend/.env.test` 加载测试 URL；测试迁移需显式启用 `TEST_MIGRATION_MODE=1`，缺少测试 URL 时不回退到开发库
-   迁移后 schema、UUID、访谈链、Audio/STT 元数据链、Message source、CASCADE / SET NULL 测试
-   GitHub Actions Backend CI：Ruff、SQLite tests、PostgreSQL fresh upgrade、Alembic check、integration tests

本地验证：

-   Ruff check / format check 通过
-   SQLite/快速测试：94 passed、2 deselected，其中包含 8 项纯配置安全测试
-   配置安全测试覆盖进程环境优先、本地 `.env.test` 加载、缺少或非测试 URL 拒绝、密码不进入错误信息、测试模式无开发库回退及正常 Alembic 模式保留
-   专用 `ai_life_memoir_test`，PostgreSQL 18.6，实际数据库名称验证通过；只操作测试库 public schema，未连接或修改开发数据库
-   空 public schema → 四个既有 migration → 唯一 head `adf9c60d178d`；upgrade/current/check 全部通过，集成测试后的 current/check 仍通过
-   实际 PostgreSQL 核心表、UUID、FK 关系链、MessageSource text/audio_transcript、CASCADE 与 SET NULL 验证通过；这是数据基础设施验证，不代表录音/STT 功能完成
-   SQLite fast tests：94 passed / 0 failed / 0 skipped / 2 deselected；PostgreSQL integration tests：2 passed / 0 failed / 0 skipped / 94 deselected
-   非阻塞警告：Starlette TestClient/httpx 弃用提示、pytest 缓存目录写入权限提示；测试退出码均为 0。无需为本轮验证修改业务代码
-   本地验证完成时 GitHub Actions workflow 已实现，远程执行当时尚未验证；后续成功结果见最终封板记录

最终封板记录（2026-10-05）：

-   Part 9.5.5-B status: Completed
-   Implementation commit: `07d1f51699b9fbcdaa09b2652be23d3349948921`，`test: add PostgreSQL integration and CI baseline`
-   Local PostgreSQL validation: PASS；Alembic fresh migration validation: PASS
-   Fast tests: PASS（94 passed / 0 failed / 0 skipped / 2 deselected）
-   PostgreSQL integration tests: PASS（2 passed / 0 failed / 0 skipped / 94 deselected）
-   GitHub Actions: Backend CI；[run 37283732708](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37283732708)，对应上述 implementation commit，master，completed / success
-   Remote CI execution verified: YES；Remote CI result: PASS。Python 3.12 / PostgreSQL 16 的远程流程包含 Ruff/format、fast tests、fresh upgrade、current/check、integration 及测试后的 current/check，均成功
-   历史交接记录：验收完成时下一项为 Part 9.5.5-C；其后已完成设计冻结，当前状态见下节
-   Part 9.5 Audio/STT 仍仅为 data/API infrastructure；真实 Audio upload、STT Provider 与生产 STT pipeline 尚未完成

### Part 9.5.5-C Family Collaboration + Participant + Consent Design Freeze

状态：

Design Frozen / Implementation Not Started。

已完成：

-   冻结 Family Collaboration、Participant、Consent、Source Provenance、Revision、Deletion、Sanitization 与 Privacy Policy 的实施设计
-   明确统一 User 身份体系、本人授权、用途隔离、历史恢复、删除传播、净化验收与 fail-safe 边界
-   形成后续 C1–C8 实施的单一设计依据：[Part 9.5.5-C Final Implementation Design Freeze](<../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md>)
-   ADR-001、003、004、005、006 为 Accepted；ADR-002、007 为 Proposed；ADR-008、009 仍为 Proposed，其中部分合同已冻结

实施边界：

-   本阶段完成的是设计封板，尚未实现 Model、Migration、Schema、Service/API、权限切换或测试
-   当前生产代码仍执行 Owner-only isolation
-   Next：C1；后续 C1–C8 依据 SSOT 实施
-   Part 9.6 Memory Extraction 保持 Planned，尚未开始

未完成：

-   Family Collaboration、Participant、Consent 的 C1–C8 实施
-   已冻结隐私状态机的代码落地、Message / Segment sequence 并发修复
-   MemoryCandidate、Memory Extraction
-   真实 Audio upload、STT Provider、AI Pipeline

下一阶段：

Part 9.5.5-C1，依据 Design Freeze SSOT 开始实施。

------------------------------------------------------------------------

## 3. 当前状态

已完成：

-   后端基础
-   用户体系
-   家庭体系
-   访谈体系
-   音频/STT数据模型

当前周期：

Part 9.5.5-C — Design Frozen / Implementation In Progress。C1 Policy + Identity Foundation、C2A Family Collaboration Foundation、C2B Interview Participant Identity Foundation — Completed / Sealed。Part 9.5.5-B — Completed / Sealed，其 Local validation: PASS、Remote CI: VERIFIED / PASS 作为历史验收记录保留。

下一阶段：

当前 Part 9.5.5-C3.1 SourceArtifact ORM Foundation — Implementation Completed within approved dormant scope；Implementation Audit = PASS WITH FINDINGS；本地 PostgreSQL 16.15 与回归验证 PASS；Staged Audit / Exact Commit Audit / Push / Remote Backend CI PASS。C3.1 implementation commit：`aa711f9b2b18ad522226b1d99afac47ea0a0dc3e`；[Backend CI run 37939418187](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37939418187)，workflow `.github/workflows/backend-ci.yml`，event push，branch master，head SHA 与 implementation commit 精确匹配，completed / success。远程 SQLite 180 passed / 48 deselected，PostgreSQL integration 48 passed / 180 deselected，均 0 failed / 0 skipped；PostgreSQL 16.15；Ruff、format（128 files）、Alembic heads / fresh upgrade / current / check / post-integration current/check PASS，单 head `d4f8a1c2b3e6`。 C3 整体 Implementation In Progress；C3.0、C2B 保持 Completed / Sealed。Final Documentation Seal：Preparation in progress。独立文档封板 commit 及其自身 exact-SHA Backend CI 尚未完成；仅在该提交推送且其 exact-SHA CI completed / success 后最终封板才生效。当前不声明 C3.1 Sealed，不预填未来 seal SHA 或 CI Run ID。C3.2 Content Artifact Integration — Next / NOT STARTED；Part 9.6 — Planned / NOT STARTED。

C3.1 仅在批准的 dormant SourceArtifact ORM foundation 范围内 Implementation Completed，不代表生产部署或完整 C3 完成。Production metadata registration、runtime Registry、content artifact_id integration、historical backfill、DerivedSource DAG、SourceSpeakerBinding、ArtifactContribution、final PostgreSQL source guards、Consent / Access Gate 和 production deletion pipeline 均 NOT IMPLEMENTED；C3-A/C3-B 均 NOT CREATED。C2B、C3.0 保持 Completed / Sealed，既有 Owner-only 内容 API 权限不变。DF-01：Deferred Medium，单语句 Family multi-path DELETE 可触发 SQLSTATE 23503，归属 C6 deletion flow / later C3 guards；L-01：Low，Starlette/httpx 弃用警告，归属 Backend dependency maintenance。

## 4. Part 9.5.5-C1 Policy + Identity Foundation 本地实施记录

日期：2026-10-05。起始 HEAD：`ade0f0ca2dbecab474d315a853b2e7721e9e9609`，master；本轮不暂存、不提交、不推送。

- 仅新增 PrivacyPolicyVersion / UserContact / AuthChallenge；User 新增 principal_kind / auth_generation，条件放宽凭据字段。既有 User 只回填 account / generation=1，不自动验证邮箱、不合并主体。
- Policy 使用显式正整数 seconds 和独立非负 retry_limit；draft 可缺参，active 必须完整且能力证据有效，发布正文不可变。没有生产默认期限。
- rights-auth challenges / verify / rights/me 为最小认证入口；rights:identity 不授予 Family 浏览、Speaker 身份或 Consent。普通账号接口保持形状；旧无类型/无 generation JWT 须重新登录。
- OTP 不保存明文，摘要由服务器密钥和 challenge 上下文绑定；校验有到期、尝试上限、事务消费、重放拒绝、渠道冲突拒绝与当前 generation / Contact 状态校验。错误响应不回显渠道或验证码。
- 生产 encryption / key lifecycle / delivery / rate limiting Provider 未接入，默认 503。测试 opaque memory vault 仅为测试替身，不是生产加密；没有新增生产密钥或默认 TTL。
- migration `c1a7d45e92b0` → down `adf9c60d178d`，单 head。真实专用 PostgreSQL 测试库 upgrade / current / check 已通过；临时 schema 空库迁移及有旧 User 的 backfill、空 C1 安全 downgrade / re-upgrade 已验证。存在 C1 证据、非 account 或 generation 变更时 downgrade 拒绝执行。没有迁移开发/生产库。
- 首轮 fast：125 passed / 17 deselected。此后新增边界用例，最终完整 fast 复验待完成，不能沿用首轮结果作为最新全量通过证明。
- 最新 PostgreSQL integration：17 passed / 139 deselected；Ruff check 通过，format check：104 files already formatted。环境存在 Starlette TestClient/httpx 弃用提示。
- 自动审批审核模型容量不足，阻止最终 fast（本地 socketpair）和 Alembic 最后复查；属于审核服务执行障碍，不是判定操作不安全。当前不满足提交验收条件。
- 未实现 FamilyMembership / FamilyInvitation / InterviewParticipant / Consent / SourceArtifact / Deletion / Sanitization / MemoryCandidate；workflow 未改动，C1 远程 CI 未运行。
- 保留 16 项既有模板删除为 unstaged；ad untouched/untracked；.env.test ignored；staging empty。冻结 SSOT 未修改，9.5.5-B Completed、C Design Frozen、C Implementation In Progress、C2 Not Started、9.6 Planned。

验收命令（Backend 目录；只允许安全 TEST_DATABASE_URL 的测试迁移模式）：

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest -m "not integration" -q -p no:cacheprovider
python -m pytest -m integration -q -p no:cacheprovider
$env:TEST_MIGRATION_MODE = '1'
python -m alembic heads
python -m alembic current
python -m alembic check
```

原结论（已由下方最终验证闭环取代）：C1 implementation written / final validation pending。本节状态优先于上文设计归档时的 Implementation Not Started 历史记录。

### C1 Final Validation Closure（2026-10-05）

- Ruff：PASS；format check：PASS（103 files already formatted）。
- 最新完整 Fast：139 passed / 0 failed / 0 skipped / 17 deselected；新增身份与安全边界测试均实际执行。
- C1 定向安全测试：45 passed / 0 failed / 0 skipped。
- PostgreSQL integration：17 passed / 0 failed / 0 skipped / 139 deselected。
- Alembic before/after：single head/current 均为 `c1a7d45e92b0`；两次 `alembic check` 均为 `No new upgrade operations detected`。
- 账号回归：register、login、users/me、Family、Interview 全部通过最新 Fast suite；rights/account token 与 principal 能力隔离通过。
- 安全审计：generation mismatch、Contact revoked、Challenge expired/locked/consumed replay、OTP 非明文、反枚举、敏感错误不回显、legacy email 不自动验证、Policy fail-safe、已发布 Policy 不可普通修改均通过。
- migration 审计：down revision、历史 User account/generation=1 backfill、数据库约束、JSONB/BYTEA/TIMESTAMPTZ、partial unique、RESTRICT FK 与 downgrade guard 符合 C1 范围；没有修改历史 migration。
- Production encryption、contact delivery、key management 与生产 rate limiter 仍为 NOT IMPLEMENTED；默认 fail closed / 503。测试内存 vault 仅为 TEST ONLY。
- 非阻塞警告：Starlette TestClient/httpx 弃用提示；pytest cache 目录 WinError 183。测试与检查退出码均为 0。
- Git：HEAD 未变、staging empty、16 项历史删除 unstaged、`ad` untracked/untouched、`.env.test` ignored；未 commit / push。

结论：C1 Implemented / Validated；Part C 仍为 Implementation In Progress；C2 Not Started / Next；Part 9.6 Planned。READY FOR C1 PRE-COMMIT AUDIT，不代表已获授权暂存或提交。

### Part 9.5.5-C1 Final Documentation Seal（2026-10-06）

- Part：9.5.5-C1 Policy + Identity Foundation。
- Status：Completed / Sealed；Part 9.5.5-C 整体仍为 Implementation In Progress。
- Implementation commit：`35ec7e33a060b07e4834091b04c2caeb852b707c`，`feat: implement policy and identity foundation`。
- Remote：`origin/master`；push 后 HEAD 与 origin/master 一致。
- Remote CI：Backend CI；Run ID `37412935434`；[Run URL](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37412935434)；completed / success。
- Local validation：Fast 139 passed / 17 deselected；targeted security 45 passed；PostgreSQL integration 17 passed / 139 deselected；Ruff PASS；Format PASS；Alembic heads/current/check 及测试后 current/check PASS。
- Security audit：Critical 0；High 0；Medium 0。
- 实施范围：PrivacyPolicyVersion、User principal_kind/auth_generation、UserContact、AuthChallenge、rights_only authentication foundation、Policy capability gate。
- 边界：rights_only authentication 不等于 Speaker identity、Consent、Source ownership 或 Family collaboration permission。
- 生产限制：encryption provider、verification delivery、key management/rotation、production rate limiting 仍未实现，默认 fail closed。
- C2：Next / Not Started；未实现 FamilyMembership、FamilyInvitation、InterviewParticipant、Consent、SourceArtifact、Deletion Pipeline、Sanitization 或 MemoryCandidate。
- Part 9.6：Planned。

## 5. Part 9.5.5-C2A Family Collaboration Foundation 历史本地实施记录

日期：2026-10-06。起始/结束 HEAD：`0add93b755422afcf69c6029c4c72879405eb98d`；本轮未暂存、未提交、未推送。

- 归档 C2 Design Addendum 和 C2A Implementation Task；C2A 与整个 C2 完成状态明确分离。
- 新增 CommandIdempotencyRecord、FamilyInvitation、FamilyMembership；`Family.owner_id` 仍是唯一 Owner 权威，FK 从 CASCADE 调整为 RESTRICT，不为 Owner 创建 Membership，不做历史业务 backfill。
- Membership 仅允许 collaborator；active/revoked/left；revoke、leave、rejoin 递增 generation；新邀请重入复用同一 `(family_id,user_id)` 行。
- Owner 邀请直接 approved；active Collaborator 邀请进入 pending_owner 并需 Owner 审批。accept 在单事务内锁定并校验 Invitation、token、context-bound proof、account/UserContact，再创建或重启 Membership并标记 Invitation accepted。
- 新增 invitation_acceptance challenge 和短期 verification_proof；严格校验 token type、scope、aud/iss、context、account、Contact 和 auth_generation。proof 不能访问 account、Family 或 rights API，也不表示 Participant verified 或 Consent。
- public mutation 使用持久化 Idempotency-Key / canonical digest；同 key 同 digest 重放 operation-specific 强类型安全 snapshot，不同 digest 返回冲突；未知 operation、错误 snapshot、额外字段和未声明嵌套对象默认拒绝。response_body 不保存 OTP、邀请明文 token、proof、Contact PII/hash/ciphertext 或 provider credential；proof 重放保持原始 `iat`/`exp`。
- 新增邀请和 Membership API。可复用 Owner / active Collaborator 门禁只用于协作管理；既有 Family/FamilyMember/Interview/Session/Audio/Transcript/Segment/Message 内容 API 继续 Owner-only。
- revision `b7e2c4d891a0` → down `c1a7d45e92b0`，单 head；新表有 CHECK、partial unique、token digest unique、Membership unique 和明确 FK 删除行为。存在 C2A 业务/幂等证据时 downgrade 拒绝。
- Audit remediation：补齐 active Collaborator 对 Family/FamilyMember/Interview/Session/Audio/Transcript/Segment/Message 的精确 404 与无内容泄露矩阵；验证其仍可发起 pending_owner Invitation。新增 Collaborator create Invitation 与 Owner revoke Membership 的 PostgreSQL 竞争测试，证明现有 Family→Membership 锁顺序线性化，并验证 revoke 后新命令拒绝、Owner 命令不受影响。
- Validation：Ruff PASS；format PASS；Fast 161 passed / 29 integration deselected；PostgreSQL integration 29 passed / 161 non-integration deselected；Alembic heads/current/check 及测试后 current/check PASS；最终 head `b7e2c4d891a0`，无 schema drift。
- PostgreSQL 覆盖 fresh isolated schema migration、JSONB/BYTEA/TIMESTAMPTZ、FK/CHECK/partial unique、身份字段和完成幂等记录不可变约束、double accept、accept/expire、approve/cancel、approve/revoke、rejoin/stale-generation、Membership revoke authorization race、duplicate invitation 和重复幂等命令的竞争结果。
- 非阻塞警告：Starlette TestClient/httpx 弃用提示；pytest cache 目录 WinError 183。所有要求的检查退出码为 0。
- 未实现 InterviewParticipant、`participant_confirmation`、Consent、Source/Provenance、RevisionProposal、Deletion、PrivacyOutbox、Sanitization、MemoryCandidate、Memory 或 Memoir；未修改 workflow，未运行生产 migration。
- Git 安全：staging empty；16 项既有模板删除继续 unstaged；`ad` 保持 untracked；`.env.test` 保持 ignored 且未输出内容。

历史结论（已由下方 Final Documentation Seal 取代）：C2A Implementation Written / Audit Remediation Completed / Pre-Commit Re-Audit Pending；C2B Next / Not Started；Part 9.6 Planned。本节保留实施与审计轨迹，不表示当前状态。

### Part 9.5.5-C2A Final Documentation Seal（2026-10-07）

- Part：9.5.5-C2A Family Collaboration Foundation。
- Status：Completed / Sealed；Part 9.5.5-C 整体仍为 Implementation In Progress。
- Implementation commit：`a33f6eb6160a2e0eb5276b0c08d9a5d9c2534cfd`，`feat: implement family collaboration foundation`。
- Migration：`b7e2c4d891a0`，down revision `c1a7d45e92b0`；单 head；未修改历史 migration，未运行生产 migration。
- Remote CI：Backend CI；Run ID [`37492358055`](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37492358055)；master；completed / success。
- Validation：Fast 163 passed / 29 deselected；PostgreSQL integration 29 passed / 163 deselected；Ruff PASS；Format PASS；Alembic heads / fresh upgrade / current / check / post-integration current/check PASS；Concurrency PASS；Security PASS。
- Audit history：Initial Pre-Commit Audit FAIL；Remediation #1 PASS；Re-Audit #1 FAIL；Remediation #2 PASS；Final Pre-Commit Re-Audit PASS WITH FINDINGS；blocking findings at seal：0。
- 实施范围：CommandIdempotencyRecord、FamilyInvitation、FamilyMembership、Owner / active Collaborator 协作管理门禁、`invitation_acceptance` context-bound verification proof、Invitation / Membership API，以及 `families.owner_id` ON DELETE RESTRICT。
- 安全边界：转发 Invitation token 拒绝；Collaborator 没有既有档案内容访问扩张；Membership revoke race 线性化；幂等响应使用 operation-specific allowlist / default deny；request fingerprint 不保存原始 recipient/token/proof/OTP canonical input；Provider 不可用时 fail closed。
- Membership 只代表 Family collaboration relation，不等于 archive content access。既有 Family、FamilyMember、Interview、Session、Audio、Transcript、Segment、Message API 仍为 Owner-only。
- 未实现：InterviewParticipant、`participant_confirmation`、ConsentGrant / ConsentEvent、Source / Provenance、RevisionProposal、Deletion Pipeline、Sanitization runtime、MemoryCandidate、Memory、Memoir。
- 生产限制：encryption provider、verification/invitation delivery、key management/rotation、production rate limiting 仍未实现；相关入口默认 fail closed。
- 下一阶段（C2A Seal 当时记录）：C2B Next / Not Started；该历史状态已由下方 C2B 本地实施记录取代。Part 9.6 Planned。

## 6. Part 9.5.5-C2B Interview Participant Identity Foundation 实施与 Remediation 记录（2026-10-07）

- 历史状态（已由下方 Final Documentation Seal 取代）：implementation commit `1038313cd57f6a76f5c6c27213912284e5af38fa` 已发布；当时 Remote CI Remediation #1 已完成本地验证，等待独立 remediation commit 与远程 CI，C2B 尚未封板。
- 新增 InterviewParticipant、speaker-only role、eligibility/state 数据库约束、稳定 Interview scope、UserContact 复合归属约束与危险 downgrade 保护。
- 新增 Owner/active Collaborator proposal、account/rights_only `participant_confirmation`、本人 context-bound confirm、成年自主决定声明、本人 inactive 和最小本人读取。
- Participant 身份关系不扩大 Family/Interview/Session/Audio/Transcript/Segment/Message 权限；verified 不产生 Consent、Source 归属、撤回或删除语义。
- migration：`d4f8a1c2b3e6`，down revision `b7e2c4d891a0`，Alembic 单 head，current/check PASS。
- Initial Pre-Commit Audit 的三个 Blocking Medium 已关闭：FamilyMember 真实删除可安全 SET NULL 且普通改绑仍拒绝；新增 `UNIQUE(id, interview_scope_id)`；补齐真实 PostgreSQL FK/CHECK/unique 与 Participant proof、rights-only、幂等安全测试。
- Fast：173 passed / 40 deselected；PostgreSQL integration：40 passed / 173 deselected；C2B PostgreSQL：11 passed；Ruff/format PASS；Alembic 空表 downgrade/re-upgrade、数据存在 downgrade guard、current/check PASS。
- PostgreSQL 验收基线：PostgreSQL 16.x，当前本地集成测试与 GitHub Actions 均使用 16.15；其他 major 版本不作为权威验收证据，major 升级必须另行完成兼容性验证。
- Remote CI Remediation #1：修正两个真实 `DELETE User` 测试的预期 SQLSTATE 为 PostgreSQL 16.15 实际返回的 `23503`；direct Participant FK 测试继续校验动态解析的约束名。16.15 本地结果：目标测试 3 passed、C2B PostgreSQL 11 passed、Fast 173 passed / 40 deselected、PostgreSQL integration 40 passed / 173 deselected、Ruff/format PASS、Alembic heads/fresh upgrade/current/check 及 post-integration current/check PASS。未修改 runtime 或 migration `d4f8a1c2b3e6`。
- Part 9.5.5-C 整体仍为 Implementation In Progress；Part 9.6 仍为 Planned。

### Part 9.5.5-C2B Final Documentation Seal（2026-10-07）

- Part：9.5.5-C2B Interview Participant Identity Foundation。
- Status：Completed / Sealed；Part 9.5.5-C 整体仍为 Design Frozen / Implementation In Progress。
- Implementation commit：`1038313cd57f6a76f5c6c27213912284e5af38fa`。
- Remediation commit：`fbb79b6a8af06b3d50e1d4923eb56169128efcde`。
- Migration：`d4f8a1c2b3e6`；down revision：`b7e2c4d891a0`。
- Remote CI：Backend CI；Run ID [`37627066699`](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37627066699)；commit `fbb79b6a8af06b3d50e1d4923eb56169128efcde`；master；completed / success；PostgreSQL 16.15。
- Validation：targeted remediation 3 passed；C2B PostgreSQL 11 passed；Fast 173 passed / 40 deselected；完整 PostgreSQL integration 40 passed / 173 deselected；Ruff PASS；Format PASS；Alembic heads / fresh upgrade / current / check / post-integration current/check PASS；最终 head `d4f8a1c2b3e6`。
- Implemented scope：InterviewParticipant；speaker-only V1 role；participant state / eligibility constraints；稳定 `interview_scope_id`；Owner / active Collaborator participant proposal；`participant_confirmation` context；context-bound identity verification；account / rights_only 本人最小 Participant access；self confirm；adult declaration；self inactive；durable idempotency reuse；verified `UserContact` ownership binding；FK / CHECK / unique / immutable scope protections；dangerous downgrade protection。
- Security / privacy boundary：Participant verified 不等于 Consent；Participant relationship 不等于 Family archive content access；FamilyMembership 不等于 archive content access。既有 Family、FamilyMember、Interview、Session、Audio、Transcript、Segment、Message 内容 API 继续保持 Owner-only，除已明确新增的 Participant 最小本人 rights path 外。
- Not implemented：ConsentGrant、ConsentEvent、SourceArtifact、Provenance、SourceSpeakerBinding、RevisionProposal、Deletion Pipeline、Privacy Ledger、Outbox、Sanitization runtime、MemoryCandidate、Memory、Memoir。
- Production limits：production encryption provider、verification / invitation delivery、key management / rotation、production distributed rate limiting 均未实现；相关入口默认 fail closed，C2B sealed 不代表 production-ready。
- Remediation history：首次 C2B implementation remote CI 在 PostgreSQL 16 上因 SQLSTATE assertion 失败；最终确认 PostgreSQL 16.15 实际 SQLSTATE 为 `23503`，remediation commit 的 exact Backend CI 已成功闭环。本地 PostgreSQL 18.6 曾观察到不同行为，因此项目冻结 PostgreSQL 16.x baseline、当前验证版本 16.15；不声明支持 PostgreSQL 18，major upgrade 必须单独完成 compatibility validation。
- Next：C3 Artifact Registry + Provenance — Next / Planned，尚未开始；Part 9.6 — Planned。

## 7. Part 9.5.5-C3.0 Final Documentation Seal（2026-10-08）

### A. Contract evidence / Seal condition

- Contract：Completed / Audited / Published；[Implementation Contract Addendum](../03_业务流程/Part9.5.5-C3_Implementation-Contract-Addendum_V1.0.md)。
- Addendum commit：`345f852d36f94752ddea99fba1f889d9d632ded0`。
- Backend CI：[Run 37762742776](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37762742776)；trigger push；exact SHA matched YES；completed / success。
- Final Seal 条件：本次文档封板提交自身的 exact-commit Backend CI 成功后才生效；当前处于 Seal Preparation，未取得未来封板提交的 CI 结果。上面的运行只证明 Addendum commit，不是封板提交证据。
- 成功的 Backend CI 只验证当前 pre-C3 Backend 基线，不证明 C3 功能已实现。

### B. Audit evidence

- Final Contract Re-Audit：PASS。
- BM-01：Sequence parent-row lock protocol CLOSED。
- BM-02：Live Artifact consistency / deletion tombstone retention CLOSED。
- BM-03：Contribution / Artifact state domains separated CLOSED。
- BM-04：Immutable provenance / controlled projection updates reconciled CLOSED。
- Critical / High / Blocking Medium：0 / 0 / 0。

### C. Frozen product scope

- Friend Option A：Owner / active Collaborator 为特定 Interview 发起参与提议；复用 User + InterviewParticipant，不要求 FamilyMembership。
- 朋友必须本人完成身份确认及自己的 SourceSpeakerBinding 确认；不自动获得 Family Archive 访问权。
- 仅被提及的第三人属于内容语义，不进行自动身份推断；人物提取属于 Part 9.6 后续独立设计。

### D. Frozen technical scope — implementation requirements only

- SourceArtifact、SourceSpeakerBinding、ArtifactContribution、DerivedSource。
- 内容与 provenance 原子注册；PostgreSQL advisory transaction lock 与 DAG guard。
- 正向及 deferred reverse consistency；按生命周期区分删除状态例外。
- Message / Segment 序号并发合同；历史确定性 backfill。
- C3-A / C3-B 属于一次 cutover 的迁移合同，不允许部分迁移独立生产 rollout。
- 以上是冻结的实施要求，不是已经完成的实现。

### E. Current limitations

- C3 runtime：NOT IMPLEMENTED。
- C3 migrations：NOT IMPLEMENTED。
- C3 PostgreSQL-specific functional tests：NOT EXECUTED。
- Consent / Access Gate：NOT IMPLEMENTED，属于 C4。
- Production invitation delivery：NOT IMPLEMENTED。
- Memory person extraction：NOT IMPLEMENTED，属于 Part 9.6。
- 后续授权处理之前，C3 不得创建 available Artifact。
- PostgreSQL baseline：16.x；当前已验证版本 16.15。

### F. Next phase

- C3.1 Registry Schema / Models — Next / Planned / NOT STARTED；仅在 C3.0 Final Seal 生效且文档封板提交 exact CI 成功后开始。
- C3 整体实施 NOT STARTED；Part 9.5.5-C 仍为 Design Frozen / Implementation In Progress；C1/C2A/C2B Completed / Sealed；Part 9.6 Planned / NOT STARTED。
- 保留 C2B sealed boundary；不修改其 runtime、状态机、确认语义、migration 或 tests。

## 8. Part 9.5.5-C3.1 SourceArtifact ORM Foundation（2026-10-08）

- 起始 HEAD / origin/master：`5f09d6c7e4c57672a85cca548cda150bc3c39c30`；master；不暂存、不提交、不推送。
- C3.0 封板闭环证据：[Backend CI 37765330926](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37765330926)，封板提交 exact SHA 匹配，completed / success；上一节 Seal Preparation 的条件现已满足。
- 状态：SourceArtifact ORM 原型已写入 / 验证未完成；不声明 C3.1 Completed。C3 整体 Implementation In Progress。
- 新建 `app/models/source_artifact.py`、`tests/test_source_artifact.py`、`tests/integration/test_source_artifact.py`、test-only `tests/integration/_source_artifact_probe.py`。
- 模型字段覆盖 UUID identity、live FK、稳定 scope、kind/entity、operator、state、显式 generation、nullable digest/locator/Policy 及 timezone-aware timestamps。state 与 generation 无隐式默认值，调用者必须显式指定。
- 具名 CHECK：四种 C3 kind、五种结构状态、generation > 0、四种 kind 要求非空 entity/interview scope、locator IS NULL。三项 UNIQUE：kind/entity、id/family scope、id/interview scope；live FK SET NULL，operator/Policy RESTRICT；scope/state、family scope/generation 和 FK 索引。
- locator 使用 JSON/JSONB none_as_null=True，只接受 SQL NULL；JSON null、任意对象/文本等均拒绝。不套用 Contribution locator 格式，无自动 digest provider 或未经合同冻结的摘要长度规则。
- 模型保持 dormant：不修改 models_import.py、models/__init__.py 或 runtime startup；不新增 C3-A/C3-B migration，Alembic head 仍为 `d4f8a1c2b3e6`。不部署 partial C3。
- SQLite 与 PostgreSQL 原型均通过子进程导入模型，父 pytest metadata 保持无 source_artifacts，不依赖执行顺序。PostgreSQL probe 使用安全 test loader，先确认实际 test DB 和 server_version_num=160015，再创建唯一临时 schema；基线迁移、原型 DDL及清理均限定该 schema，前后 baseline Alembic check 不作弱化。
- 实际验证：Ruff PASS；format PASS（128 files）；新增 SQLite 原型 7 passed / 0 failed / 0 skipped；完整 Fast 180 passed / 0 failed / 0 skipped / 48 deselected；Alembic heads：`d4f8a1c2b3e6 (head)`。
- PostgreSQL 前置检查：共用 loader 的目标为 `ai_life_memoir_test`，实际 server_version_num=180006（18.6），不符合 16.15。已停止数据库写入验证；未执行本轮 upgrade/current/check 或 integration tests，未创建 prototype schema。PostgreSQL 原型与完整 baseline 回归均待安全配置指向 16.15 后验证；不把本次连接成功记为 integration PASS。
- 未读取或输出 .env.test 原文、完整 TEST_DATABASE_URL 或密码；loader 按项目规则内部加载。未连接开发/生产库，未修改开发或测试数据库 schema/data。
- 限制：未实施 runtime Registry 注册、content artifact_id、原子内容注册、历史 backfill、正向/反向 guards、scope immutability trigger、状态转换 guard、DAG、Speaker Binding、Contribution、Consent / Access Gate。模型 CHECK 不等于这些最终 PostgreSQL guards。
- 下一步：补齐 PostgreSQL 16.15 验证，再做 C3.1 Implementation Audit；后续 C3.2 Content Artifact Integration。Part 9.6 Planned。
- 非阻塞环境提示：Python launcher real-location 提示；Starlette TestClient/httpx 弃用提示。完整 fast 在允许本地 socket 的环境中通过；沙箱内首轮停在 TestClient，已中断，未用该次运行作为成功证据。


## 9. Part 9.5.5-C3.1 PostgreSQL Prototype Remediation（2026-10-09）

- 当前状态：Implementation Written / Local Validation PASS / Implementation Audit Pending；尚未封板。C3.0 保持 Completed / Sealed；C3 整体 Implementation In Progress；Part 9.6 Planned / NOT STARTED。
- 安全门禁：共用 loader，TEST_MIGRATION_MODE=1；配置与实际连接为 127.0.0.1:55432 / ai_life_memoir_c3_test；server_version_num=160015。不使用开发 DATABASE_URL，不输出凭据；原型实验仅使用本次创建的唯一临时 schema 并清理该 schema。
- 首次真实 16.15 回归：基线 fresh upgrade/current/check PASS；SourceArtifact 8 setup errors；完整 PostgreSQL 40 passed / 8 errors / 180 deselected；SQLite fast 180 passed / 48 deselected。失败不计为通过。
- H-01：pg_constraint / pg_get_constraintdef 实测 family/interview/session live FK 均为 ON DELETE SET NULL，与模型一致。父链与 Artifact 已 flush，删除 Family 复现 SQLSTATE 23503 / source_artifacts_interview_id_fkey；移除该事务中所有前置拒绝操作后仍复现，savepoint 回滚后事务 active，排除前置失败污染。相同数据逐项删除 Session、Interview、Family 时三个 SET NULL 均通过且稳定 scope 不变，问题归于多路径 cascade 的引用动作执行顺序。
- 最小修复仅调整测试：用显式标注的 test-only erased 结构 fixture 逐项证明 live FK SET NULL，保留各阶段剩余 FK 与稳定 scope 断言、非法 FK/RESTRICT/rollback 验证；未改模型或约束。该 fixture 不实现 C3 创建/状态转换或 C6 删除授权。单条 Family 多路径 cascade 的 PostgreSQL 16.15 机械限制未被改写为已修复，后续合法删除流程需单独处理。
- 合同解释：最终 live-state Artifact 的普通 hard DELETE/cascade 孤儿必须由后续反向 guards 拒绝；终态结构测试不证明最终删除 pipeline、合法授权或生产删除功能。C3.1 不实施这些 guards 或 C6。
- M-01：Alembic Config 在构造时绑定 stdout，redirect_stdout 单独使用不能捕获 command.check 的 Config.print_stdout。改为显式 Config(stdout=io.StringIO())，异常继续传播；两个父测试 fixture 均增加 stdout 恰为单行 JSON 的协议断言并解析 JSON，不接受失败子进程。
- 修复后验证：定向 FK 1 passed / 7 deselected；SourceArtifact PostgreSQL 模块 8 passed；完整 PostgreSQL integration 48 passed / 180 deselected；SQLite fast 180 passed / 48 deselected（含 SourceArtifact 7 passed）；均为 0 failed / 0 errors / 0 skipped。Ruff PASS；format PASS（128 files）。
- Alembic heads/current/check 及原型 schema 内前后 check PASS；基线唯一 head 仍为 d4f8a1c2b3e6，无 schema drift。C3-A/C3-B 未创建、未生产部署。
- 本轮仅修复三个既有 C3.1 测试文件，同步 README、路线图、本日志；SourceArtifact 保持 dormant，无生产 metadata 注册，C2B、C3.0 Addendum、CI workflow 未改动。未连接开发/生产库；16 个历史删除、untracked ad、ignored .env.test 保留，暂存区为空；未 stage/commit/push。
- Next：C3.1 Implementation Audit；审计及仓库流程完成前不封板、不启动 C3.2。C3.1 远程 CI 尚未验证，既有 C3.0 CI 不作为本轮功能验证证据。非阻塞提示：Starlette TestClient/httpx 弃用警告。

### C3.1 Final Implementation Audit（2026-10-09）

- Implementation Audit：PASS WITH FINDINGS；Critical 0、High 0、Blocking Medium 0。
- PostgreSQL 16.15：verified，server_version_num = 160015；Targeted PG 8 passed；Full PG integration 48 passed；SQLite fast 180 passed；Ruff / Format / Alembic：PASS。
- DF-01：Deferred Medium，Family multi-path DELETE limitation；Owner：C6 / later C3 guards。L-01：Low，Starlette/httpx warning；Owner：Backend dependency maintenance。
- Precise Staging：seven expected files staged；Staged Audit：documentation consistency finding under correction；Repository seal pending。
- Commit / Push / Remote CI：not completed at time of entry。Next：Staged Audit recheck。

## 10. Part 9.5.5-C3.1 Implementation Commit + Remote CI Closure（2026-10-09）

- Implementation：Completed within approved dormant ORM foundation scope；Implementation Audit：PASS WITH FINDINGS；Staged Audit：PASS；Exact Commit Audit：PASS。
- Implementation commit：`aa711f9b2b18ad522226b1d99afac47ea0a0dc3e`；message：`feat(backend): add dormant C3.1 SourceArtifact foundation`；parent：`5f09d6c7e4c57672a85cca548cda150bc3c39c30`。
- Commit contents：7 files / 4 Added / 3 Modified / 0 Deleted。一次普通 push 成功，实际 origin/master 与 implementation SHA 匹配。
- Backend CI：[Run 37939418187](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37939418187)；workflow：`.github/workflows/backend-ci.yml`；event：push；branch：master；head SHA：`aa711f9b2b18ad522226b1d99afac47ea0a0dc3e`；status：completed；conclusion：success。
- Local validation：SourceArtifact PostgreSQL 8 passed；完整 PostgreSQL integration 48 passed / 180 deselected；SQLite fast 180 passed / 48 deselected；0 failed / 0 errors / 0 skipped；PostgreSQL 16.15；Ruff / format / Alembic PASS。
- Remote CI validation：PostgreSQL 16.15；PostgreSQL integration 48 passed / 180 deselected；SQLite fast 180 passed / 48 deselected；0 failed / 0 skipped；Ruff PASS；format PASS（128 files）；Alembic single heads / fresh upgrade / current / check / post-integration current/check PASS；单 head `d4f8a1c2b3e6`。
- Audit：Critical 0、High 0、Blocking Medium 0。
- C3.1 仅在批准的 dormant SourceArtifact ORM foundation 范围内 Implementation Completed，不代表生产部署或完整 C3 完成。Production metadata registration、runtime Registry、content artifact_id integration、historical backfill、DerivedSource DAG、SourceSpeakerBinding、ArtifactContribution、final PostgreSQL source guards、Consent / Access Gate 和 production deletion pipeline 均 NOT IMPLEMENTED；C3-A/C3-B 均 NOT CREATED。C2B、C3.0 保持 Completed / Sealed，既有 Owner-only 内容 API 权限不变。DF-01：Deferred Medium，单语句 Family multi-path DELETE 可触发 SQLSTATE 23503，归属 C6 deletion flow / later C3 guards；L-01：Low，Starlette/httpx 弃用警告，归属 Backend dependency maintenance。
- Final Documentation Seal：Preparation in progress。独立文档封板 commit 及其自身 exact-SHA Backend CI 尚未完成；仅在该提交推送且其 exact-SHA CI completed / success 后最终封板才生效。当前不声明 C3.1 Sealed，不预填未来 seal SHA 或 CI Run ID。C3.2 Content Artifact Integration — Next / NOT STARTED；Part 9.6 — Planned / NOT STARTED。
- 本节更新当前状态；前述实施、环境阻塞、remediation 和审计记录保留为历史证据。本次为文档封板准备，不执行 seal commit、push、tag 或 C3.2 实施。


## Memory + Memoir MVP Vertical Slice 1（2026-10-11）

> 历史实施与验证记录保留如下；当前结论以本节末“最新核验状态同步”为准。

本节更新当前业务开发主线；前述 C3/BM-01 历史记录与已有编辑保留。当前阶段：Memory + Memoir Slice 1 代码完成 / SQLite 验证通过 / PostgreSQL 验证待执行。C3 不因此完成或启用。

- 已实现：Owner-only 人工结构化 Memory 创建、读取、分页列表、更新；每条 Memory 固定关联一个同一 FamilyMember 的原始 InterviewMessage。保留时间原话、地点、情感，不改写 Message / Segment。
- 已实现：同一 FamilyMember 的选定 Memory 按请求顺序确定性组装 Memoir draft；保存 MemoirSection 标题/正文快照、position 与 memory_id；可读取草稿及有序章节。Memory 后续更新不会覆盖已有章节。
- API：POST/GET /api/v1/family-members/{member_id}/memories；GET/PATCH /api/v1/memories/{id}；POST /api/v1/family-members/{member_id}/memoirs；GET /api/v1/memoirs/{id}；GET /api/v1/memoirs/{id}/sections。复用 JWT 与既有 Owner-only 权限，不开放协作者内容权限。
- 迁移源码：e8c2a9b47106 -> down_revision d4f8a1c2b3e6；新增 memories / memoirs / memoir_sections。静态解析确认唯一 head e8c2a9b47106；未执行 upgrade/downgrade/current/check，未连接真实 PostgreSQL。
- 本轮实际测试：新增及既有认证/家庭/访谈/消息/音频/转写/健康 API 回归 97 passed；最终新增模块复测 11 passed；Ruff check 与 format --check（14 个相关 Python 文件）PASS；1 条既有 Starlette/httpx 弃用警告。不是全仓测试或 PostgreSQL 验收。
- 测试隔离：每用例独立内存 SQLite、FK 开启，结束后释放；执行进程禁用 dotenv 读取与第三方 pytest 自动插件，拦截所有非内存 SQLite Engine.connect。沙箱内 Windows TestClient socketpair 初始化停滞，诊断进程已退出，两个停滞进程已中断；经执行审批在沙箱外运行相同数据库门禁测试通过。未读取 .env.test，未使用历史数据库。
- 验证分类：SQLite PASS；真实 PostgreSQL NOT RUN / PENDING；真实数据库清理 N/A（未创建资源）；无本任务遗留数据库资源。未操作 Docker、BM-01、Git staging/commit/push。
- 已覆盖：来源追踪、原文保持不变、跨用户/家庭/人物关联拒绝、非法/不存在 ID、认证、统一 404、422/INVALID_SOURCE、分页、章节顺序与快照、Memory/Memoir 写入失败 rollback、来源外键保护。
- 待执行集成验证：在未来专项授权的唯一可丢弃 PostgreSQL 数据库验证迁移/ORM 一致性、FK/CHECK/UNIQUE、事务、删除冲突及并发行为；本任务没有新增 PostgreSQL 用例，不把 SQLite 当作真实 PostgreSQL 证据。
- 限制：仅人工 Memory 和确定性草稿；无 MemoryCandidate/正式审批/版本历史、AI Provider、RAG、writer 编辑、支付或自动 STT。每条 Memory 一个来源；source association 不可更新；章节顺序由创建请求指定，尚无创建后重排 API。
- 限制：引用采用 RESTRICT 保留证据链，已有家庭/人物/访谈删除在存在新引用时可能报外键错误；本任务未改写既有删除 API，应后续补合法删除流程与冲突响应。同人物约束由 Service 实施，尚无跨表 PostgreSQL guard。C3 provenance、C4 Consent/Access Gate 与 C6 删除传播未接入，不宣称生产就绪或本人授权已满足。
- Next MVP：补充 Memory 审查/版本与合法删除冲突契约，再独立验收 PostgreSQL。下一 AI Agent milestone（Part 9.7）：独立 AI Service 接口及访谈追问，输出仅写 assistant/ai_generated Message；须先满足来源/Consent/Provider 门禁，不直接写正式 Memory。本 slice 不表示 Part 9.6 AI Extraction 或 Part 9.7 已上线。



**最新核验状态同步（2026-10-11，依据项目 Owner 提供的独立复审结果）**

- Memory + Memoir MVP Slice 1：Implementation completed；代码实现与安全复审在限定范围内完成。Independent Code Security Gate：PASS within reviewed code scope；该结论不代表 HTTP、PostgreSQL 或生产验收通过。
- Finding decisions：MM-01 CLOSED — code / SQLite scope；MM-01-R01 CLOSED — code / SQLite scope；MM-02 CLOSED — code / offline scope。MM-01-R01 删除入口采用 Owner-scoped Interview 查询，现有他人 ID 与不存在 ID 使用等价的 404 正文；保留 MM-01 引用冲突 409、rollback 与 RESTRICT 保护。
- 最新独立证据：18 passed / 0 failed / 0 skipped / 16 deselected；Independent probes：3 passed。两组证据分别记录，不相加为唯一测试用例数；本次文档同步没有运行测试。
- HTTP API Gate：BLOCKED / NOT RUN。原因：当前沙箱条件阻止所选 ASGI 测试路径的获批执行。历史实施测试与 collect-only 记录保留，不替代当前 HTTP API Gate。
- PostgreSQL migration/integration：NOT RUN；路线图 PostgreSQL integration：PENDING。Concurrency：NOT VERIFIED on real PostgreSQL；SQLite / mock 结果不作为真实 PostgreSQL 验证。
- Remaining findings：MM-03 OPEN — Low — bounded N+1 queries；MM-04 OPEN — Low — test dependency override restoration。两项均未在本轮实现或关闭。
- 当前阶段：Memory + Memoir Slice 1 code implementation and security review completed at limited scope；Git development snapshot：PREPARATION IN PROGRESS；HTTP API validation：BLOCKED。
- Release classification：DEVELOPMENT SNAPSHOT ONLY；NOT PRODUCTION READY。下一主线里程碑：AI Interview Agent MVP；本次不启动后续开发。
- BM-01 remains OPEN and separate；不改变任何无关 C3 milestone 状态或历史结论。Git development snapshot 尚未 staging、commit 或发布，本次文档同步不授权这些操作。

## MM-01 / MM-02 Targeted Remediation（2026-10-11）

> 历史实施与验证记录保留如下；当前结论以本节末“最新核验状态同步”为准。

本节更新 Slice 1 当前状态：定向修复已实现 / 离线 SQLite Service 验证通过 / 独立复审待执行；不自批准封板，不启动下一 Slice。前述记录保留为历史。

- 基线：master，HEAD fb5c384dca15bef16b9ee350d04081ac2f8ceb04；编辑前索引为空，已记录九个拟修改文件 SHA-256。仅修改授权的六个 Service/CRUD 文件、test_memory_memoir.py 及本日志/路线图。
- MM-01：Interview / FamilyMember 删除先完成 Owner 授权，再检查受保护 Memory/Memoir 引用；冲突返回 409 / RESOURCE_IN_USE / 通用脱敏消息。删除 CRUD 只 flush，由 Service commit；flush/commit 失败均 rollback。PostgreSQL 仅识别 SQLSTATE 23503 + 指定保护 FK 名 + 目标表；SQLite 仅识别 FK 错误码/固定错误文本并复核保护引用。其他 IntegrityError 保持原异常，不泛化为 409。未新增 Session/Message 删除接口，未更改 RESTRICT。
- MM-02：Memory/Memoir 改为经 FamilyMember -> Family.owner_id 过滤的查询；GET/PATCH Memory、GET Memoir/sections 的他人及不存在 ID 返回一致资源类型的 NOT_FOUND 正文。正文查询仅命中 Owner 范围；原始来源与跨人物校验保留。
- 实际执行：沙箱内新增离线 Service/CRUD 测试 16 passed / 14 deselected，1 条既有 Starlette/httpx 警告。每例独立内存 SQLite，实测 foreign_keys=ON；dotenv 读取及其他数据库连接被进程门禁禁止，无 TestClient 实例运行。
- 证据分类：SQLite 真实 FK flush 失败及 rollback/data preservation PASS；PostgreSQL SQLSTATE/constraint-name/table-name 分类与 flush/commit 失败仅为模拟验证。覆盖他人/缺失 404 完整 JSON、正常 Owner 读取、跨家庭/人物源拒绝、正常无引用删除、草稿排序/快照/分页及无关 IntegrityError 不误转 409。
- NOT RUN / BLOCKED：40 个 API 用例完成安全 collect-only（含 3 个新增定向 API 用例及既有回归），未执行 TestClient；当前任务禁止绕过沙箱限制，沿用已知 Windows socketpair 阻塞条件，不申请沙箱外运行。真实 PostgreSQL、迁移、并发及生产验收均 NOT RUN / PENDING；无真实资源创建或清理，cleanup N/A。
- MM-03 / MM-04：仍为 Low / 待处理；本任务未提供具体发现正文，不推断内容、不宣称已修复。
- 已知边界：Family DELETE 不在本轮授权内；既有空引用但含 Interview 的 FamilyMember ORM 删除可能发生其他完整性错误，未将其误映射为引用冲突；完整删除/Consent/版本历史仍待后续专项任务。上述两项修复尚待独立复审及 HTTP/真实 PostgreSQL 验证。
- 下一计划里程碑仍为独立 AI Interview/Agent：AI Service 访谈追问、assistant/ai_generated Message；依赖来源/Consent/Provider 门禁。本轮不开始该里程碑，不调用模型。
- Git 安全：未 stage/commit/push/reset/clean；既有 16 个删除、ad、BM-01 文件、其他 Slice 文件和既有文档编辑保留；未读取 .env.test 或 secrets，未连接 PostgreSQL、执行迁移或操作 Docker。

**最新核验状态同步（2026-10-11，依据项目 Owner 提供的独立复审结果）**

- Memory + Memoir MVP Slice 1：Implementation completed；代码实现与安全复审在限定范围内完成。Independent Code Security Gate：PASS within reviewed code scope；该结论不代表 HTTP、PostgreSQL 或生产验收通过。
- Finding decisions：MM-01 CLOSED — code / SQLite scope；MM-01-R01 CLOSED — code / SQLite scope；MM-02 CLOSED — code / offline scope。MM-01-R01 删除入口采用 Owner-scoped Interview 查询，现有他人 ID 与不存在 ID 使用等价的 404 正文；保留 MM-01 引用冲突 409、rollback 与 RESTRICT 保护。
- 最新独立证据：18 passed / 0 failed / 0 skipped / 16 deselected；Independent probes：3 passed。两组证据分别记录，不相加为唯一测试用例数；本次文档同步没有运行测试。
- HTTP API Gate：BLOCKED / NOT RUN。原因：当前沙箱条件阻止所选 ASGI 测试路径的获批执行。历史实施测试与 collect-only 记录保留，不替代当前 HTTP API Gate。
- PostgreSQL migration/integration：NOT RUN；路线图 PostgreSQL integration：PENDING。Concurrency：NOT VERIFIED on real PostgreSQL；SQLite / mock 结果不作为真实 PostgreSQL 验证。
- Remaining findings：MM-03 OPEN — Low — bounded N+1 queries；MM-04 OPEN — Low — test dependency override restoration。两项均未在本轮实现或关闭。
- 当前阶段：Memory + Memoir Slice 1 code implementation and security review completed at limited scope；Git development snapshot：PREPARATION IN PROGRESS；HTTP API validation：BLOCKED。
- Release classification：DEVELOPMENT SNAPSHOT ONLY；NOT PRODUCTION READY。下一主线里程碑：AI Interview Agent MVP；本次不启动后续开发。
- BM-01 remains OPEN and separate；不改变任何无关 C3 milestone 状态或历史结论。Git development snapshot 尚未 staging、commit 或发布，本次文档同步不授权这些操作。

## Part 9.6-A — AI Interview Agent MVP Mock（2026-10-11，最新阶段状态）

> 本节为新的开发阶段状态记录；此前 Memory + Memoir Slice 1、Part 9.5.5-C3、BM-01 的历史记录和既有编辑不作覆盖。原路线图关于“9.6 Extraction / 9.7 Agent”的描述保留为当时的规划；实际交付编号现按项目 Owner 决定采用 9.6-A（Mock Agent）、9.6-B（Candidate + Review）、9.6-C（获准后的真实 Provider 接入）。

- **当前阶段 / 周期**：Part 9.6-A Mock Agent — implementation completed；independent static code review `PASS WITH FINDINGS`；M01 remediation `PASS — eligible for closure`，由 Owner 批准 **CLOSED（仅静态代码审查范围）**；最终 HTTP、真实 PostgreSQL 与生产验证未完成。下一主线为 9.6-B 设计与最小实施范围审批。
- **仓库基线**：`master`，HEAD `8421f1d725ec6b7e98c6f1a54a52f78d4fdee085`（Memory + Memoir Slice 1 已推送的开发快照）。Part 9.6-A 的 19 个实现文件及后续两文件 M01 修复尚未获得 Git staging、commit 或 push 授权；不把本地实现描述为已经提交或远端 CI 通过。
- **实施范围**：14 个新增文件、5 个既有文件局部修改，共 19 个（Backend Agent Router/Schema/Service/Client/CRUD/Model、测试、Alembic revision `f3a96b10d207`，以及独立 AI Service 的契约、确定性 Mock 和测试）。无需 LangGraph；无运行中的跨服务传输，也无真实 LLM 接入。
- **功能**：`GET /api/v1/sessions/{session_id}/agent-state`；`POST /api/v1/sessions/{session_id}/agent-turns`（`start / answer / skip / end`，UUID `Idempotency-Key`、`expected_version`，`answer` 需要 `answer_message_id`）。Agent 状态 `idle → awaiting_answer → ended`；一次提出一个简短问题，根据规则和关键词追问、跳过、题库耗尽自动结束。Mock 仅证明固定规则分支，不代表真实自然语言理解。
- **原文、权限与事务**：原始 `user/text` 或已保存的原始来源 Message 不改写；Assistant 问题由服务端以 `assistant / ai_generated` 保存。新查询执行 JWT 和 `Family.owner_id` 范围过滤；他人与不存在资源使用非泄漏的完整 404。Assistant Message、AgentState、AgentTurn 在同一事务完成；失败只回滚派生写入，不删除既存答案。重放重新核查权限及处理许可；幂等请求指纹不含老人答案正文。
- **消息序号与迁移**：用户、转写及 Agent 消息通过共享 Session 级写入协调分配 `sequence`；ORM 与 Alembic 新增 `UNIQUE(session_id, sequence)`。新迁移 `f3a96b10d207` 的父版本为 `e8c2a9b47106`；迁移源码会检查历史重复序号并明确失败，不自动重编号。仅完成源码和静态检查，**未执行真实 PostgreSQL 迁移、并发/行锁验证或 `alembic current/check`**。
- **Consent / 来源安全边界**：生产默认 `503 / POLICY_UNAVAILABLE`，不使用客户端 `consent=true` 代替有效授权；许可拒绝时 AI Client 零调用，来源内容在权限/许可判定前不加载。逐来源真实 Consent/讲述者授权与外部 Provider 条件仍未实现；仅允许合成数据和注入式 Mock 权限进行离线验证。Family Owner 权限不等于讲述者处理许可。
- **审计**：19 文件独立代码审计 `PASS WITH FINDINGS`，未发现明确 Critical/High；`9.6A-M01`（删除 Assistant 问题导致 `ON DELETE SET NULL` 后幂等重放返回不完整成功结果）经两文件定向修复，并由独立只读复审确认 **CLOSED — STATIC CODE REVIEW SCOPE ONLY**。重放现在针对原本预期输出却已缺失的 Turn 返回 `409 / IDEMPOTENCY_RESULT_UNAVAILABLE`，合法无输出的 end/题库耗尽不受影响。`9.6A-L01`（`idle → end`、新键 `ended → end` 可继续生成 Turn/版本）的 Low 语义问题保持 **OPEN**，未作暗中行为变更。
- **测试证据分级**：Codex A 首次实施报告：Backend 离线 42 passed / 2 deselected、Memory/Memoir 定向 Service 回归 18 passed、AI Service Mock 10 passed；这些分组单独记录，缺原始执行日志，独立审计未复现。M01 修复后，Codex A 报告专用隔离命令 `python -I -B ".../apps/backend/tests/test_interview_agent.py"`，退出码 0，`51 passed in 2.90s`（38 个原 Service 用例 + 13 个 M01 参数化新增用例）；Codex B 已静态核查测试断言、文件哈希与修复范围，但 **未独立运行测试，也未取得原始终端输出**。所有上述 passed 数字属于实施者报告结果，不得写成独立复现或全仓验证。
- **当前 NOT RUN / NOT VERIFIED**：HTTP/ASGI 请求路径 NOT RUN；真实 PostgreSQL upgrade/current/check、外键、事务及集成 NOT RUN；PostgreSQL `READ COMMITTED` 并发、行锁及幂等竞争 NOT VERIFIED；真实 Consent、真实 AI Provider、STT、RAG、Candidate 审核和生产部署 NOT IMPLEMENTED。`MM-03`、`MM-04` 和 `BM-01` 保持原有未关闭状态；不改 C3 各阶段原结论。
- **下一阶段**：Part 9.6-B — Memory Candidate + immutable Revision + human review。拟从有真实来源引用的原始 Message 提取候选，保留推断/不确定性与证据、允许人工纠正和审核；批准后才原子创建正式 Memory。A/B 合成 Mock 范围与未来 C 的真实 Consent/Provider 范围须分开审批，不能提前生产处理真实人生经历。
- **发布分类**：`DEVELOPMENT SNAPSHOT ONLY / NOT PRODUCTION READY`。本记录是本地状态同步，不表示新的 Git commit、push、CI、真实数据库迁移或生产审批已完成。


## Part 9.6-A Provider Extension — 合同草案归档（2026-10-12）

> 本节为合同起草时的历史记录；其待审查 / 未实施状态已由下方最新独立审查状态取代。合同正文保留起草与工程澄清记录，不作为最新交付状态。

- **归档文档**：[Scope Freeze + Implementation Contract V1.0](../04_AI设计/Part9.6-A_Provider-Extension_Implementation-Contract_V1.0.md)，为本子阶段详细草案的唯一来源；其他项目文档仅保留摘要和引用。
- **状态**：Product Scope CONFIRMED；Engineering Contract COMPLETE DRAFT — PENDING REVIEW / APPROVAL；Status **DRAFT — PENDING INDEPENDENT REVIEW**；Implementation **NOT STARTED**。21 文件实施白名单、字段、约束、拟用 migration revision 与 API 等工程设计待独立审查和批准；本次未生成或执行迁移。
- **基线**：HEAD `8421f1d725ec6b7e98c6f1a54a52f78d4fdee085`，另依赖现有未提交的 9.6-A 工作区实现；实施前须核验相关文件 SHA-256。
- **本次范围**：新建完整合同草案，向 README、路线图和本日志追加摘要与链接。未修改代码、配置、测试或 workflow，未运行测试，未操作数据库 / Docker，未暂存、提交或推送；既有工作区内容保留。
- **下一步**：独立合同审查并取得实施批准；9.6-B 继续为 Candidate + Revision + Human Review，9.6-C 继续为获批后的真实 Provider 接入。既有 9.6-A 静态审查结论、开放发现及 NOT RUN / NOT VERIFIED 项目沿用前节记录。

## Part 9.6-A Provider Extension — Independent Review PASS + Documentation Sync（2026-10-12，最新阶段状态）

依据项目 Owner 提供的《Part 9.6-A Provider Extension Independent Review Report》结论同步。本轮核对合同及相关实现的状态表述，未重新执行独立审查或测试；不新增测试数量、迁移成功或远端 CI 证据。

| 项目 | 当前状态 |
| --- | --- |
| Implementation | Completed（Provider Extension 源码及离线增量范围） |
| Contract Compliance | PASS |
| Independent Code Review | PASS（源码审查及本轮无数据库验证范围） |
| Critical / High / Medium / Low Finding | 0 / 0 / 0 / 0（仅本次 Provider Extension 独立审查范围） |
| 修复要求 | 无 |
| Documentation Sync | Completed（本日志与路线图） |
| Git Commit Readiness Review / Staged Audit | PENDING / NOT RUN |
| Git staging / Commit / Push | 未授权；本轮未执行 |

- **交付闭环**：9.6-A Mock Agent → M01 修复 → Provider Extension Contract → Provider Extension Implementation → Independent Review PASS。原 Mock / M01 审查及合同草案记录保留为历史，不将本次 PASS 扩展为全仓安全结论或生产验收。
- **Provider 架构**：`interview-agent.v2` Request/Result 合同、AIProvider 接口、显式 Registry 与 Mock Provider 已形成可替换的离线边界。DeepSeek / GPT / 本地模型 / LangGraph 适配及 Backend→AI Service 实际跨服务传输仍待后续独立实施；不把接口扩展写成真实 Provider 已接入。
- **事务与幂等**：准备上下文并预留 Turn / commit → 数据库事务及锁之外的同步 Provider 边界 → 重新校验后发布结果 / commit。同一 Idempotency-Key 绑定请求指纹；pending 重放不再次调用，completed 重放复核权限、许可与输出可用性；failed / discarded 为终态，无自动重试或 orphan pending 自动恢复。上述源码合同不构成外部 Provider exactly-once 调用保证或真实 PostgreSQL 并发证明。
- **v2 访谈语义**：AgentState 为 `idle / listening / paused / ended`；start 进入 listening，保存原始文字不触发 Provider，只有显式 request_question 请求问题，成功后仍为 listening。pause 后仍可保存文字，resume 不补发问题；end 将 AgentState 置 ended 并原子完成 Session，不结束 Interview。Session completed 后三个 Message 写入入口拒绝新增。`awaiting_answer` 仅属 legacy v1；Session completed 与 Turn execution_status 不混作 AgentState。
- **迁移源码**：Provider Extension revision `a196e4c72b08`，parent `f3a96b10d207`；原 Mock migration 与前置实现属于后续提交范围核对对象。本轮没有执行迁移，也没有将 21 文件实施白名单直接当作 Git 提交白名单。
- **权限与历史发现**：既有内容 API 保持 Owner-only；ProcessingDecision 默认关闭，Mock 许可只用于合成离线验证。Operator / Owner 不替代 Speaker / Consenter；真实 Consent、C3 Provenance / Access Gate / 删除传播未因此完成。历史 `9.6A-L01`、`MM-03`、`MM-04` 及 C3/BM-01 保持原有范围与状态，不由本次零发现结论自动关闭。

| 未完成或未验证项目 | 保留状态 |
| --- | --- |
| HTTP/ASGI 完整请求链 | NOT RUN |
| PostgreSQL Migration / Integration | NOT VERIFIED；本轮未执行 |
| PostgreSQL 并发 / 行锁 | NOT VERIFIED |
| Real Provider | NOT IMPLEMENTED（后续 9.6-C） |
| Consent 真实流程 | NOT IMPLEMENTED |
| 生产部署 | NOT STARTED |
| 真实数据库清理 | N/A（本轮未创建资源） |

**发布分类**：DEVELOPMENT SNAPSHOT ONLY / NOT PRODUCTION READY。真实数据库验证仍须遵循 Backend AGENTS 的独立 Manager / 受限 Runner、唯一可丢弃数据库及专项授权规则；Mock 或源码审查 PASS 不授权真实 provisioning。

**近期门禁**：Documentation Sync → Git Commit Readiness Review → 获授权的精确暂存与 Staged Audit → Commit Authorization → Push Authorization。提交评审须核对原 9.6-A 前置修改、M01 和 Provider Extension 文件、迁移链及文档，排除无关 C3/BM-01、历史模板删除与 `ad`；本轮不执行暂存审计、commit 或 push。

**下一功能阶段**：Part 9.6-B — Candidate + immutable Revision + Human Review，待最小实施范围审批；9.6-C 保留为获批后的真实 Provider 接入。本轮只同步两份文档，保留所有既有工作区改动，未修改 runtime、迁移、测试、配置或 workflow，未运行应用/测试、操作 PostgreSQL / Docker 或写入 Git 索引。

## Part 9.6-A Provider Extension Completed（2026-10-12）

依据项目 Owner 确认的 Implementation Completed 与 Independent Review PASS 同步；前述 Mock、M01、合同草案及上一轮两份文档同步记录均保留为历史。本轮仅同步四份指定文档，未复跑实施测试或独立审查，不新增测试数量或验证证据。

**完成范围：Offline Provider Extension**

- Provider Contract v2
- Offline Mock Provider
- Agent transaction separation：预留并提交 → 事务与锁外调用 → 重新校验并发布
- Pause/Resume/End lifecycle：pause 后可保存文字，resume 不补发，end 完成 Session
- Message lifecycle protection：Session 完成后拒绝三个 Message 写入入口新增消息

**Independent Review：PASS**

**限制：**

- HTTP/ASGI NOT VERIFIED（完整请求链沿用 NOT RUN 记录）
- PostgreSQL NOT VERIFIED（迁移、集成及并发仍未验证）
- Real Provider NOT IMPLEMENTED

**历史发现：**9.6A-L01 保留为 v1 duplicate end semantics issue，继续独立跟踪，不因本次 PASS 关闭；当前 v2 对新 key 重复 end 返回冲突，同 key 幂等重放保留。MM-03、MM-04 与 C3/BM-01 的历史范围和状态保持原记录。

**下一阶段：Part 9.6-B Candidate + Revision + Human Review**

**发布分类：DEVELOPMENT SNAPSHOT ONLY**

**本轮文档同步：**README、开发日志、路线图与合同首页/历史状态说明已同步。Git：no add / no commit / no push，未执行 reset / restore / clean；Database：no operation；Docker：no operation；未执行 migration，未读取 .env 或 secret，未修改业务代码。完成后停止，不进入 Git Commit。


## Part 9.6-B — 完善设计草案并归档（2026-10-12）

**任务：Documentation Only。** 用户授权完善审批、API、迁移与验收合同并纳入项目；未授权代码实施、测试执行或 Git 写操作。

- **当前基线**：实际本地 master HEAD `6c12e96e4f83ada7cb7c7dd60fec4283269f8700`，message `feat(interview): add provider extension for interview agent`。本次未进行远端查询或推送；之前的 Git 待提交记录保留为历史。
- **详细 SSOT**：[Part 9.6-B Candidate + Immutable Revision + Human Review Contract V1.0](../04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。
- **产品范围**：单条原始文字显式提取；新批次保留旧候选；统一不可变人工/AI Revision；Owner 批准精确版本；新 Memoir 绑定精确 Memory Revision/proof；历史数据 Legacy，未知本人授权 fail closed。
- **工程完善**：单一 RevisionProposal 的 offline_memory.v1 profile、表字段与精确 FK、审批/CAS、相关用途 generation、三阶段批次和迟到结果、敏感 HMAC/key 轮换、安全控制路径、旧 API 切换、迁移与 downgrade guard、48 项验收以及 36 个拟实施源码文件。该拟范围不是已批准实现或暂存白名单。
- **同步范围**：新建合同；README、路线图、本日志、ADR-008、Memory 生成链路文档保留摘要/引用；不把全部表结构复制到其他文档。ADR-008 保持 Proposed。
- **状态**：产品决定 CONFIRMED；工程合同 REFINED DRAFT — PENDING INDEPENDENT CONTRACT REVIEW；9.6-B IMPLEMENTATION NOT STARTED / NOT AUTHORIZED；9.6-C FUTURE / NOT STARTED。
- **证据分类**：本次仅源码/文档核对及归档一致性复核；未运行任何实施测试、HTTP/ASGI、PostgreSQL、迁移或真实 Provider。源代码审查、合成结果与生产验收不互相替代；未新增测试数量、CI 成功或清理完成结论。
- **安全范围**：未修改 runtime、migration、tests、workflow、配置、AGENTS、C3/BM-01；保留16项历史模板删除、ad untracked 与 .env.test ignored；不读 secret；未 add/commit/push/reset/restore/clean。
- **下一步**：独立合同审查后由用户批准离线实施；不因本次归档自动启动 9.6-B。

## Part 9.6-B — 独立合同审查后的最小文档修订（2026-10-12）

用户提供正式独立报告：PASS WITH FINDINGS，Critical0 / High0 / Medium2 / Low1。审查旧合同 hash `1C2BB83312240154FED858C7D1F1FB2A13DBCCC5255DFAEAC5CDCCA11FA9302A`；实际本地基线仍master @ `6c12e96e4f83ada7cb7c7dd60fec4283269f8700`，暂存区空。此前归档记录的36文件/48验收为原审查范围。

**本次只修订文档，P01–P11不变。**

- B-CR-01：真实代码表明HTTP mapper没有请求Session可回滚；旧ORM Parent DELETE可能先置NULL。合同§10.3明确3个Service持有事务、3个CRUD只改delete为参数化单目标Core DELETE＋flush、新workflow CRUD只提供scope metadata EXISTS、准确PG manifest与SQLite回滚后引用核验、DEBUG安全边界。拟实施文件增6，**42=20新增＋22修改**；没有实际修改这6个源码。
- B-CR-02：撤销五秒实际调用上界声明，仅验收Stub主动TimeoutError的安全分类；实际deadline/中断在后续真实Provider设计，不新添假配置。
- B-CR-03：已有目标及Proposal按API表要求版本，新建批次/manual Candidate/Memoir例外；旧禁用POST/PATCH不新增头/版本要求。
- 审查补充建议：同key恢复查询仅返回pending/原终态/unknown；暂缺记录不能成为自动重执行依据。验收新增B49–B57，共**57项未来场景**。
- 同步README、路线图、本日志、ADR-008、Memory链路摘要；详细SSOT仍为 [9.6-B合同](../04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。ADR-008继续Proposed。
- 当前状态：**REVISED DRAFT — PENDING TARGETED RE-REVIEW；IMPLEMENTATION NOT STARTED / NOT AUTHORIZED**。不能把合同修订当成运行时漏洞已修复，也不能自动关闭正式报告finding或批准42文件实施。
- 未运行测试/应用/HTTP/PG，不生成或执行migration、不使用DB/Docker，不读.env/secret、不写Git。保留全部既有未提交内容、16历史模板删除、ad、C3/BM-01和AGENTS。

# ADR-001 — Orchestrator 组合化演进(技术债登记)

- **Status:** Accepted(登记技术债,暂不重构)
- **Date:** 2026-08-18
- **Related:** docs/01_ARCHITECTURE.md、docs/14_ROADMAP.md

## 背景

Phase A 实现了最小 `Orchestrator`(确定性重试/升级);Phase B 通过
`RecoveringOrchestrator(Orchestrator)` 子类化复用了 executor 处理层
(超时/crash/结果终态与事件),只替换决策层。两条路径都被测试与实验记录
锁定,Phase A baseline 刻意保持零改动。

## 现状

```
orchestrator.py          # Phase A: Task→Run→Attempt→Executor→Result→EventStore
orchestrator_v2.py       # Phase B: + Validator → Classifier → RecoveryPolicy → ContextBuilder
```

共享:attempt 循环骨架、executor 执行与超时处理、事件发射、仓库写入。
差异:决策层(validation/classification/recovery/context)。

## 技术债

若继续按"新阶段复制整个 Orchestrator"演进,将长成:

```
orchestrator.py
orchestrator_v2.py
orchestrator_v3.py   # ← 禁止
orchestrator_v4.py
```

每次复制都带来:事件顺序漂移、修复不同步、测试矩阵翻倍。

## 决策

1. **现在不重构。** Phase A baseline 的冻结价值 > 结构美感;重构会触碰
   已被 EXP-RUNTIME-001/002 锁定的行为,且 Phase C 有更高优先级的工作。
2. **演进方向(Phase C 完成后、出现第三个变体需求时执行)**:收敛为单一
   `Orchestrator`,决策点全部通过组合注入:

   ```
   Orchestrator
        │
        ├── ValidationPolicy
        ├── RecoveryPolicy
        ├── ContextPolicy
        └── Executor(factory)
   ```

   - Phase A 的 deterministic 策略 = `RecoveryPolicy` 的一个实现;
     Phase B 的闭环 = 各 Policy 的默认实现组合。
   - **版本体现在 Policy 与 Harness Version,不体现在复制 Orchestrator。**
   - 重构验收:EXP-RUNTIME-001/002 的 Stage 0/Stage B 事件链在重构后逐字节一致。
3. **短期纪律**:新增 orchestrator 变体前,先为共享骨架提取 mixin/基类,
   禁止整文件复制。

## 影响

- 无立即行为变化;docs/12 的 Harness Version 规则不受影响。
- 未来 Phase C Job 场景的 `JobValidator` 直接作为 `ValidationPolicy` 注入,
  不需要第三个 Orchestrator 文件。

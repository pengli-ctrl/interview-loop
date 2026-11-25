# Demo 素材

本目录保存 InterviewLoop 的公开展示素材合成数据和重新捕获脚本，不包含真实候选人的简历、录音或面试记录。

## 目录

```text
demo/
  interview-loop.gif       # 10 帧端到端演示
  screenshots/             # 产品页面截图
  assets/
    demo_resume.txt        # 虚构简历
    demo_jd.txt            # 虚构岗位 JD
  .capture/                # 脚本运行时生成的隔离数据，不入库
```

## 截图

| 页面 | 文件 |
|---|---|
| 工作台 | [dashboard.png](screenshots/dashboard.png) |
| 设置第一步 | [setup.png](screenshots/setup.png) |
| JD/简历上下文 | [setup-context.png](screenshots/setup-context.png) |
| 确认与授权 | [setup-confirm.png](screenshots/setup-confirm.png) |
| 面试室 | [interview.png](screenshots/interview.png) |
| 文字作答 | [interview-answer.png](screenshots/interview-answer.png) |
| 复盘报告 | [report.png](screenshots/report.png) |
| 成长记录 | [growth.png](screenshots/growth.png) |
| 管理控制台 | [admin.png](screenshots/admin.png) |
| 评估指标 | [admin-evaluation.png](screenshots/admin-evaluation.png) |

## 重新生成

```powershell
pip install -r requirements-dev.txt
python -m playwright install chromium
python scripts/capture_demo.py
```

捕获脚本会：

- 启动隔离的 Demo 候选服务和管理服务；
- 使用 `demo/assets/demo_jd.txt` 与 `demo_resume.txt` 完成一次文字回答流程；
- 生成真实结构化报告和成长记录数据；
- 输出全部截图并合成 `interview-loop.gif`；
- 结束后停止服务。

如需使用已有服务：

```powershell
python scripts/capture_demo.py --external-servers --candidate-port 8502 --admin-port 8503
```

Demo 数据库、日志和临时帧位于 `demo/.capture/`，已被 `.gitignore` 排除。

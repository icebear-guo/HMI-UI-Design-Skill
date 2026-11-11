# 生成真实评审记录

由助手依据已发生的对话填入，不让客户写JSON。输入是`hmi-review-evidence/1.0`，与输出记录放在同一项目目录；阶段目录/入口使用项目内相对路径。

```json
{
  "schema": "hmi-review-evidence/1.0",
  "project_revision": "r1",
  "page_ids": ["overview", "parameters"],
  "stages": {
    "parameters": {
      "revision": "p1",
      "status": "awaiting_customer",
      "artifact_dir": "review/parameters-p1",
      "entry": "project-brief.md"
    }
  }
}
```

`prepare_review_record.py --evidence review-evidence.json --out workflow-r1.json`读取实际文件生成SHA和依赖。没有真实回复就用`awaiting_customer`，未开始阶段保持pending；不为了通过校验伪造同意。交互阶段还需`pages:[{"id":"overview","entry":"overview.html"}, ...]`对应实际文件，页面ID须与范围一致。

状态为confirmed时，输入stage的`customer_confirmation`提供实际`customer_message/message_ref/confirmed_at`；工具计算对应版本的`reviewed_digest`，不会生成客户原话。时间用带时区的ISO值。明确自主委托则提供顶层`delegation`：`mode:"delegated"`、实际`stages`、`customer_message/message_ref/recorded_at/project_revision`，相应阶段状态用delegated，不能把委托伪记成人工确认。

阶段快照内的既有PNG可在`existing_assets`列相对路径；不能将新生产素材标成既有资产来绕过评审。此工具不改变快照、不代替客户判断，也不审批HTML即时复制。输出后用`check_project_workflow.py --record workflow-r1.json --for samples|ui|delivery`报告现有证据状态，blocked不等于需要重新向已经明确授权的事项索要许可。

import os
from pathlib import Path

import streamlit as st


def _get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, default)).strip()


LLM_API_KEY = _get_secret("deepseek_api_key")
LLM_BASE_URL = _get_secret("deepseek_base_url", "https://api.deepseek.com/v1")
LLM_MODEL = _get_secret("deepseek_model", "deepseek-chat")
VOLC_API_KEY = _get_secret("volc_api_key")
VOLC_APPID = _get_secret("volc_appid")
VOLC_TOKEN = _get_secret("volc_token")
VOLC_TTS_RESOURCE_ID = _get_secret("volc_tts_resource_id", "seed-tts-2.0")
VOLC_ASR_RESOURCE_ID = _get_secret("volc_asr_resource_id", "volc.seedasr.auc")
VOICE_TYPE = _get_secret("volc_voice_type", "zh_female_vv_uranus_bigtts")

BASE_DIR = Path(__file__).resolve().parent.parent
SAVE_DIR = BASE_DIR / "interview_sessions"
SAVE_DIR.mkdir(parents=True, exist_ok=True)
GLOBAL_STATS_PATH = BASE_DIR / "weak_stats_mode.json"
RECORD_DIR = BASE_DIR / "面试记录"
RECORD_DIR.mkdir(parents=True, exist_ok=True)
MAX_RESUME_BYTES = 10 * 1024 * 1024

# 面试轮次配置
MODE_CONFIG = {
  "技术一面": {
    "desc": "基础原理、编码、中间件、项目基础细节",
    "tags": [
      "MCP概念",
      "Temporal",
      "OTel",
      "可观测",
      "RPC/订阅",
      "RAG",
      "基础原理",
      "编码能力"
    ],
    "default_style": "温和",
    "stage_list": [
      {
        "name": "自我介绍",
        "desc": "简单自我介绍，职业经历概述",
        "pool": [
          "简单做一下自我介绍，重点讲你的工作经历和技术方向。"
        ],
        "question_plan": [
          "自我介绍：工作年限、主要技术方向、当前职责"
        ],
        "max_followups": 0,
        "time_budget_min": 5
      },
      {
        "name": "项目概览",
        "desc": "挑选你最核心的项目，整体介绍",
        "pool": [
          "介绍一下你简历里最有代表性的项目，项目背景、目标、你承担的角色。"
        ],
        "question_plan": [
          "选择一个最具代表性的项目，说明业务背景、目标、团队规模和个人职责"
        ],
        "max_followups": 1,
        "time_budget_min": 6
      },
      {
        "name": "项目深挖",
        "desc": "项目架构、实现、难点",
        "pool": [
          "这个项目的整体架构是什么样？",
          "项目里遇到最大的技术难点是什么，怎么解决的？"
        ],
        "question_plan": [
          "项目整体架构、核心模块和技术选型",
          "关键难点、解决方案、取舍和最终效果"
        ],
        "max_followups": 2,
        "time_budget_min": 20
      },
      {
        "name": "基础技术高频题",
        "desc": "后端、AI Agent、中间件基础原理",
        "pool": [
          "解释RPC原理，订阅模式怎么实现异步流程？",
          "说说RAG的整体流程和常见坑？",
          "说说OTel Collector的Agent和Gateway区别？"
        ],
        "question_plan": [
          "RAG/Agent 核心流程、常见问题和边界",
          "RPC、消息队列和分布式系统基础",
          "可观测性、稳定性和故障排查"
        ],
        "max_followups": 1,
        "time_budget_min": 15
      },
      {
        "name": "简单系统设计",
        "desc": "轻量架构设计",
        "pool": [
          "如果要做一个多租户的工具调用平台，你会怎么设计？"
        ],
        "question_plan": [
          "设计支持长流程的 Agent 编排与工具调用平台，覆盖可靠性、幂等、扩展性和可观测性"
        ],
        "max_followups": 3,
        "time_budget_min": 10
      },
      {
        "name": "候选人反问",
        "desc": "你向面试官提问",
        "pool": [
          "你有什么想向我了解的？"
        ],
        "question_plan": [
          "候选人向面试官提问"
        ],
        "max_followups": 0,
        "time_budget_min": 4
      }
    ]
  },
  "技术二面": {
    "desc": "架构设计、高并发、稳定性、故障治理、性能优化",
    "tags": [
      "架构设计",
      "落地细节",
      "边界条件",
      "可观测",
      "Agent编排",
      "高并发",
      "故障治理"
    ],
    "default_style": "压力面",
    "stage_list": [
      {
        "name": "自我介绍",
        "desc": "精简自我介绍",
        "pool": [
          "简单自我介绍，重点讲你负责的架构和项目。"
        ],
        "question_plan": [
          "简要介绍工作经历、架构职责和当前技术方向"
        ],
        "max_followups": 0,
        "time_budget_min": 4
      },
      {
        "name": "项目概览",
        "desc": "复杂项目整体介绍",
        "pool": [
          "介绍你最复杂的落地项目，业务规模、QPS、约束条件。"
        ],
        "question_plan": [
          "介绍最复杂的落地项目，说明业务规模、QPS、团队和约束条件"
        ],
        "max_followups": 1,
        "time_budget_min": 6
      },
      {
        "name": "项目深度深挖",
        "desc": "取舍、故障、性能、瓶颈",
        "pool": [
          "当时架构选型为什么这么选，有没有其他备选方案？",
          "线上出现过什么严重故障，排查链路是什么？"
        ],
        "question_plan": [
          "复杂项目的整体架构、边界划分和关键设计",
          "高并发、稳定性和线上故障治理的实际案例"
        ],
        "max_followups": 2,
        "time_budget_min": 20
      },
      {
        "name": "进阶技术题",
        "desc": "分布式、可观测、Agent编排",
        "pool": [
          "Outbox模式的风险和边界是什么？",
          "MCP和自研RPC插件模式的异同？",
          "Grafana、Loki、Tempo整套可观测链路怎么协同？"
        ],
        "question_plan": [
          "分布式一致性、事务和消息可靠性",
          "可观测性体系和性能优化方法",
          "Agent 编排、MCP 和平台架构"
        ],
        "max_followups": 1,
        "time_budget_min": 15
      },
      {
        "name": "系统设计",
        "desc": "高并发、稳定性设计",
        "pool": [
          "设计一个支持长流程的Agent编排平台，要考虑重试、断点、幂等。"
        ],
        "question_plan": [
          "设计高并发、多租户的 Agent 工具调用平台，说明扩展性、限流、容灾和成本"
        ],
        "max_followups": 3,
        "time_budget_min": 12
      },
      {
        "name": "候选人反问",
        "desc": "你向面试官提问",
        "pool": [
          "你有什么想向我了解的？"
        ],
        "question_plan": [
          "候选人向面试官提问"
        ],
        "max_followups": 0,
        "time_budget_min": 3
      }
    ]
  },
  "技术三面": {
    "desc": "技术负责人、技术选型、团队管理、业务权衡、长期规划",
    "tags": [
      "架构设计",
      "落地细节",
      "管理经验",
      "Agent编排",
      "技术选型",
      "风险权衡",
      "团队建设"
    ],
    "default_style": "压力面",
    "stage_list": [
      {
        "name": "自我介绍",
        "desc": "负责人视角自我介绍",
        "pool": [
          "自我介绍，重点讲团队管理、技术建设经历。"
        ],
        "question_plan": [
          "从技术负责人视角介绍管理范围、技术建设和业务贡献"
        ],
        "max_followups": 0,
        "time_budget_min": 4
      },
      {
        "name": "重点项目复盘",
        "desc": "从负责人视角复盘项目",
        "pool": [
          "站在负责人角度，复盘你主导的一个大型项目，做得好和不足的地方。"
        ],
        "question_plan": [
          "复盘你主导的最复杂项目，说明目标、结果和关键决策",
          "复盘团队或技术体系建设中的成功与不足"
        ],
        "max_followups": 2,
        "time_budget_min": 18
      },
      {
        "name": "技术决策深挖",
        "desc": "选型、权衡、风险",
        "pool": [
          "做技术选型时，你怎么平衡稳定性、迭代速度、成本？",
          "如果团队内部技术路线分歧，你怎么处理？"
        ],
        "question_plan": [
          "说明一次重要技术选型及备选方案、风险和最终结果",
          "面对稳定性、迭代速度和成本冲突时如何决策"
        ],
        "max_followups": 1,
        "time_budget_min": 12
      },
      {
        "name": "团队与工程建设",
        "desc": "团队、流程、技术体系搭建",
        "pool": [
          "如果你接手一个后端团队，你会优先搭建哪些工程体系？"
        ],
        "question_plan": [
          "如何搭建团队研发流程、质量体系和人才培养机制",
          "如何处理团队分歧、绩效和人员风险"
        ],
        "max_followups": 1,
        "time_budget_min": 12
      },
      {
        "name": "战略与业务思考",
        "desc": "业务结合技术长期规划",
        "pool": [
          "AI Agent平台商业化落地，你觉得最大的卡点是什么？"
        ],
        "question_plan": [
          "AI Agent 平台商业化的关键卡点、机会和投入优先级",
          "技术路线与业务目标的长期协同"
        ],
        "max_followups": 1,
        "time_budget_min": 10
      },
      {
        "name": "候选人反问",
        "desc": "你向面试官提问",
        "pool": [
          "你有什么想向我了解的？"
        ],
        "question_plan": [
          "候选人向面试官提问"
        ],
        "max_followups": 0,
        "time_budget_min": 4
      }
    ]
  },
  "HR面": {
    "desc": "职业规划、离职原因、沟通、抗压、薪资、协作",
    "tags": [
      "职业规划",
      "离职原因",
      "沟通表达",
      "抗压能力",
      "薪资谈判",
      "团队协作"
    ],
    "default_style": "温和",
    "stage_list": [
      {
        "name": "自我介绍",
        "desc": "综合自我介绍",
        "pool": [
          "做一下自我介绍。"
        ],
        "question_plan": [
          "综合介绍职业经历、优势和求职方向"
        ],
        "max_followups": 0,
        "time_budget_min": 5
      },
      {
        "name": "离职与求职动机",
        "desc": "离职原因、为什么看新机会",
        "pool": [
          "为什么从上一家公司离开？为什么想应聘这个岗位？"
        ],
        "question_plan": [
          "说明离职原因、岗位选择和长期动机"
        ],
        "max_followups": 1,
        "time_budget_min": 9
      },
      {
        "name": "协作与冲突",
        "desc": "团队协作、矛盾处理",
        "pool": [
          "和同事/产品有分歧的时候，你怎么处理？"
        ],
        "question_plan": [
          "说明一次跨团队冲突或低效协作，以及你的处理方式和结果"
        ],
        "max_followups": 1,
        "time_budget_min": 11
      },
      {
        "name": "职业规划",
        "desc": "短期、长期规划",
        "pool": [
          "未来3年你的职业规划是什么？"
        ],
        "question_plan": [
          "说明未来 1～3 年的职业目标和能力建设计划"
        ],
        "max_followups": 1,
        "time_budget_min": 9
      },
      {
        "name": "抗压与加班",
        "desc": "抗压、工作节奏",
        "pool": [
          "你怎么看待加班，如何平衡工作生活？"
        ],
        "question_plan": [
          "说明你如何应对高压、加班和优先级冲突"
        ],
        "max_followups": 1,
        "time_budget_min": 9
      },
      {
        "name": "薪资预期与反问",
        "desc": "薪资、候选人反问",
        "pool": [
          "你的薪资预期是多少？",
          "你有什么想问我的？"
        ],
        "question_plan": [
          "说明薪资预期、底线和其他关键条件",
          "候选人向面试官提问"
        ],
        "max_followups": 0,
        "time_budget_min": 17
      }
    ]
  }
}
MODE_LIST = list(MODE_CONFIG.keys())
STYLE_LIST = ["温和", "压力面"]


"""Generate benchmarks/job-v0.1/jobs/JD-*.json (JOB-V0.1, locked).

The JD contents below are hand-authored (not model-generated) and constitute
the locked dataset. This script is idempotent: re-running it must reproduce
the committed JSON byte-for-byte. Run from repo root:

    uv run python scripts/generate_job_dataset.py

Candidate reference (CAND-001 张一诺, candidate_profile_v1):
  2026 届本科, 深圳; skills: React/TS/Python/FastAPI/Node.js/MySQL,
  LLM API(OpenAI/DeepSeek)/RAG 基础/Prompt/Coze/Dify/Agent 编排;
  internship 6 months (3 AI 应用 + 3 前端); no full-time experience.
  career_goal_v1: targets AI 应用/Agent/AI 全栈/AI Coding/AI 前端;
  avoid: pure model training, pure algorithm research;
  location: 深圳/广州/远程.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS_DIR = ROOT / "benchmarks" / "job-v0.1" / "jobs"

# (job_id, company, title, location, remote, source, url,
#  posted_date, expires_at, job_type, degree_required,
#  graduate_year_required, experience_required, jd_text,
#  requirements[], responsibilities[])
JDS = [
    # ------------------------------------------------------------- HIGH (10)
    ("JD-001", "深圳市星穹智能科技有限公司", "AI Agent 应用开发工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-001",
     "2026-05-20", "2026-09-30", "AI Agent", "本科", "2026", "应届/实习",
     "负责面向企业的 AI Agent 应用开发,基于 LLM API 构建智能助手与自动化流程。",
     ["React/TypeScript 前端开发", "Python 后端开发", "LLM API 集成", "Agent 应用开发经验(项目或实习)", "良好的沟通与文档能力"],
     ["智能助手对话界面开发", "Agent 工作流编排与调试", "LLM 调用链路优化"]),
    ("JD-002", "深圳市启明数字科技有限公司", "AI 应用全栈工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-002",
     "2026-05-15", "2026-09-15", "AI 全栈", "本科", "2026", "应届",
     "负责 AI 应用产品前后端全栈开发,将大模型能力集成进业务系统。",
     ["React/TypeScript", "Python/FastAPI", "LLM API 调用", "全栈项目经验"],
     ["AI 功能前后端联调", "产品功能迭代", "LLM 调用封装"]),
    ("JD-003", "广州市幻影网络科技有限公司", "Agent 应用开发工程师", "广州", False, "校招官网", "https://careers.example.com/jobs/jd-003",
     "2026-04-10", "2026-08-31", "AI Agent", "本科", "2026", "应届",
     "开发多轮对话与任务型 Agent,服务于营销与客服场景。",
     ["Python", "Agent 编排(Coze/Dify 或 LangChain 均可)", "RAG 基础", "多轮对话系统理解"],
     ["Agent 流程搭建", "知识库问答链路开发", "对话效果调优"]),
    ("JD-004", "深圳市光年互动科技有限公司", "AI 前端工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-004",
     "2026-05-01", "2026-09-01", "AI 前端", "本科", "2026", "应届",
     "负责 AI 产品前端交互开发,打造大模型对话与生成式界面。",
     ["React/TypeScript", "前端工程化(Vite/Webpack)", "LLM 交互界面经验", "组件化开发"],
     ["对话式 UI 组件开发", "流式输出渲染优化", "前端工程化建设"]),
    ("JD-005", "深圳市代码星河科技有限公司", "AI Coding 应用工程师", "深圳", False, "内推平台", "https://careers.example.com/jobs/jd-005",
     "2026-05-25", "2026-09-25", "AI Coding", "本科", "2026", "应届",
     "基于 LLM 构建代码生成与代码分析工具,提升研发效率。",
     ["LLM API(OpenAI/DeepSeek)", "Python", "代码生成/代码分析工具理解", "React 基础"],
     ["代码补全与审查工具开发", "LLM 提示词与后处理链路", "开发者工具前端界面"]),
    ("JD-006", "深圳市云端智能有限公司", "大模型应用开发工程师", "远程", True, "校招官网", "https://careers.example.com/jobs/jd-006",
     "2026-05-10", "2026-09-10", "AI 应用", "本科", "2026", "应届",
     "远程协作开发大模型应用,面向文档问答与知识管理场景。",
     ["LLM API", "RAG", "Python", "远程协作能力"],
     ["RAG 应用开发", "文档知识库问答", "线上协作与异步沟通"]),
    ("JD-007", "深圳市知行智能科技有限公司", "AI 应用研发工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-007",
     "2026-04-20", "2026-08-20", "AI 应用", "本科", "2026", "应届",
     "负责 AI 应用后端服务研发,支撑大模型能力在业务中稳定落地。",
     ["Python/FastAPI", "LLM API", "MySQL", "后端服务开发"],
     ["AI 服务接口开发", "数据存储与查询优化", "LLM 调用限流与降级"]),
    ("JD-008", "广州市数智新星科技有限公司", "AI 全栈开发工程师", "广州", False, "校招官网", "https://careers.example.com/jobs/jd-008",
     "2026-05-18", "2026-09-18", "AI 全栈", "本科", "2026", "应届",
     "开发 AI 驱动的企业应用,覆盖前端交互与后端服务。",
     ["React/Node.js", "Python", "LLM API", "全栈项目经验"],
     ["企业 AI 应用全栈开发", "前后端联调", "AI 功能集成"]),
    ("JD-009", "深圳市灵犀智能有限公司", "LLM Agent 开发工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-009",
     "2026-05-22", "2026-09-22", "AI Agent", "本科", "2026", "应届",
     "开发客服与助理类 Agent 产品,负责智能体流程与工具调用设计。",
     ["Python", "Agent 框架(Coze/Dify 等)", "LLM API", "Prompt 工程", "客服/助手类产品经验"],
     ["Agent 工具调用设计", "Prompt 模板维护", "客服机器人对话质量优化"]),
    ("JD-010", "深圳市未来视界科技有限公司", "AI 应用开发工程师(智能体方向)", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-010",
     "2026-06-01", "2026-10-01", "AI 应用", "本科", "2026", "应届",
     "开发智能体类 AI 应用,探索 Agent 在内容生成与办公场景的落地。",
     ["智能体应用", "React", "LLM API", "Python"],
     ["智能体应用开发", "前端交互界面", "LLM 功能联调"]),
    # ----------------------------------------------------------- MEDIUM (10)
    ("JD-011", "深圳市矩阵基础设施有限公司", "AI Infra 工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-011",
     "2026-05-12", "2026-09-12", "AI Infra", "本科", "2026", "应届",
     "负责 AI 服务的基础设施与推理部署,保障模型服务稳定高效。",
     ["Docker/K8s", "GPU 推理部署", "Python", "云服务(AWS/阿里云)"],
     ["模型服务容器化部署", "推理服务监控与告警", "云资源成本优化"]),
    ("JD-012", "深圳市深度算法科技有限公司", "AI 算法工程师(应用方向)", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-012",
     "2026-05-08", "2026-09-08", "Agent 算法", "本科", "2026", "应届",
     "负责模型的微调与训练流程,并参与部分 LLM 应用落地。",
     ["PyTorch", "模型微调/训练", "部分 LLM 应用", "扎实的数学基础"],
     ["模型微调实验", "训练数据处理", "评估指标分析"]),
    ("JD-013", "深圳市星辰后端科技有限公司", "后端开发工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-013",
     "2026-04-15", "2026-08-15", "普通后端", "本科", "2026", "应届",
     "负责业务系统后端开发,支撑高并发交易场景。",
     ["Java/Spring Boot", "MySQL", "分布式基础", "接口设计与性能优化"],
     ["业务接口开发", "数据库表设计", "线上问题排查"]),
    ("JD-014", "深圳市像素前端科技有限公司", "前端开发工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-014",
     "2026-05-05", "2026-09-05", "纯前端", "本科", "2026", "应届",
     "负责 ToB 产品前端开发,打造高质量业务界面。",
     ["React/TypeScript", "前端工程化", "性能优化", "组件库开发"],
     ["业务页面开发", "前端性能优化", "组件库维护"]),
    ("JD-015", "深圳市质量立方科技有限公司", "AI 产品测试开发工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-015",
     "2026-05-14", "2026-09-14", "测试开发", "本科", "2026", "应届",
     "负责 AI 产品的测试体系与自动化建设,保障 AI 功能质量。",
     ["测试框架", "Python", "AI 产品测试", "自动化测试"],
     ["AI 功能测试用例设计", "自动化测试脚本", "质量数据看板"]),
    ("JD-016", "深圳市数据星河科技有限公司", "数据分析工程师(AI 方向)", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-016",
     "2026-05-16", "2026-09-16", "AI 应用", "本科", "2026", "应届",
     "负责业务数据分析与 AI 辅助分析应用开发。",
     ["SQL", "Python 数据分析", "机器学习基础", "BI 工具"],
     ["数据报表开发", "分析模型搭建", "AI 辅助分析应用"]),
    ("JD-017", "深圳市云端部署科技有限公司", "AI 应用开发工程师(需部署经验)", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-017",
     "2026-05-19", "2026-09-19", "AI 应用", "本科", "2026", "应届",
     "开发 AI 应用并要求具备基本的部署与运维能力。",
     ["LLM 应用", "Docker/K8s 部署", "CI/CD", "Python/React"],
     ["AI 应用开发", "服务容器化部署", "CI/CD 流水线维护"]),
    ("JD-018", "深圳市三维视觉科技有限公司", "AI 前端工程师(WebGL/3D 方向)", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-018",
     "2026-05-21", "2026-09-21", "AI 前端", "本科", "2026", "应届",
     "负责 AI 3D 内容工具的前端开发,基于 WebGL 呈现生成式 3D 内容。",
     ["React", "WebGL/Three.js", "3D 渲染", "TypeScript"],
     ["3D 场景前端开发", "渲染性能优化", "AI 生成内容展示"]),
    ("JD-019", "深圳市向量引擎科技有限公司", "大模型应用开发(需向量数据库深度)", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-019",
     "2026-05-23", "2026-09-23", "AI 应用", "本科", "2026", "应届",
     "负责大规模知识库检索与 RAG 应用开发,要求对检索链路有深入理解。",
     ["RAG 深度", "Milvus/向量数据库", "检索优化", "Python"],
     ["向量检索链路开发", "召回效果调优", "知识库系统建设"]),
    ("JD-020", "深圳市敏捷智能有限公司", "AI 应用工程师", "深圳(可远程)", True, "校招官网", "https://careers.example.com/jobs/jd-020",
     "2026-05-24", "2026-09-24", "AI 应用", "本科(硕士优先)", "2026", "1 年以上应用开发经验(实习可折算)",
     "开发 AI 应用产品,支持远程办公;硕士学历优先但不作为硬性要求。",
     ["LLM 应用", "React/Python", "加分:硕士学历", "加分:开源项目"],
     ["AI 应用功能开发", "跨团队协作", "线上文档与异步沟通"]),
    # -------------------------------------------------------------- LOW (10)
    ("JD-021", "深圳市往届招聘有限公司", "AI 应用工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-021",
     "2026-05-11", "2026-08-11", "AI 应用", "本科", "2025", "仅限 2025 届",
     "仅面向 2025 届毕业生招聘 AI 应用工程师,2026 届请勿投递。",
     ["LLM API", "Python", "仅限 2025 届毕业生"],
     ["AI 应用开发", "LLM 功能集成"]),
    ("JD-022", "深圳市高端人才有限公司", "AI 全栈工程师", "深圳", False, "内推平台", "https://careers.example.com/jobs/jd-022",
     "2026-05-09", "2026-09-09", "AI 全栈", "硕士", "2026", "应届",
     "招聘硕士学历 AI 全栈工程师,负责企业级 AI 平台建设。",
     ["React/TypeScript", "Python/FastAPI", "LLM API", "硕士学历(硬性要求)"],
     ["AI 平台全栈开发", "AI 能力中台建设"]),
    ("JD-023", "北京市中关村智能科技有限公司", "大模型应用工程师", "北京", False, "校招官网", "https://careers.example.com/jobs/jd-023",
     "2026-05-13", "2026-09-13", "AI 应用", "本科", "2026", "应届",
     "工作地点北京,负责大模型应用开发,要求到岗办公。",
     ["LLM API", "Python", "北京到岗(不提供远程)"],
     ["大模型应用开发", "业务系统 AI 化改造"]),
    ("JD-024", "上海市浦江智能科技有限公司", "AI 前端工程师", "上海", False, "校招官网", "https://careers.example.com/jobs/jd-024",
     "2026-05-17", "2026-09-17", "AI 前端", "本科", "2026", "应届",
     "工作地点上海,负责 AI 产品前端开发,要求到岗办公。",
     ["React/TypeScript", "LLM 交互界面", "上海到岗(不提供远程)"],
     ["AI 前端开发", "对话界面构建"]),
    ("JD-025", "深圳市硬件星辰有限公司", "嵌入式 AI 工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-025",
     "2026-04-25", "2026-08-25", "AI 应用(嵌入式)", "本科", "2026", "应届",
     "负责端侧 AI 推理的嵌入式实现,面向智能硬件场景。",
     ["C/C++", "嵌入式开发/单片机", "RTOS", "端侧推理框架"],
     ["嵌入式 AI 推理移植", "硬件驱动开发"]),
    ("JD-026", "深圳市预训练大模型研究院", "大模型训练算法工程师", "深圳", False, "内推平台", "https://careers.example.com/jobs/jd-026",
     "2026-05-02", "2026-09-02", "Agent 算法", "硕士", "2026", "应届",
     "负责大模型预训练与对齐研究,要求硕士学历与扎实的算法功底。",
     ["预训练/RLHF", "PyTorch 底层", "分布式训练", "硕士学历(硬性要求)"],
     ["模型预训练实验", "对齐训练(RLHF)"]),
    ("JD-027", "上海市前沿算法研究院", "AI 算法研究员", "上海", False, "校招官网", "https://careers.example.com/jobs/jd-027",
     "2026-04-30", "2026-08-30", "Agent 算法", "硕士", "2026", "应届",
     "从事 AI 算法研究,鼓励发表顶会论文;要求硕士及以上学历。",
     ["算法研究", "论文发表", "扎实数学功底", "硕士及以上学历(硬性要求)"],
     ["前沿算法研究", "论文撰写与发表"]),
    ("JD-028", "广州市旧届招聘有限公司", "2025 届 AI 前端工程师", "广州", False, "校招官网", "https://careers.example.com/jobs/jd-028",
     "2026-05-06", "2026-08-06", "AI 前端", "本科", "2025", "仅限 2025 届",
     "仅面向 2025 届毕业生招聘 AI 前端工程师。",
     ["React/TypeScript", "LLM 交互界面", "仅限 2025 届毕业生"],
     ["AI 前端开发", "对话界面构建"]),
    ("JD-029", "深圳市迟暮科技有限公司", "AI Agent 应用开发工程师", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-029",
     "2026-02-15", "2026-05-31", "AI Agent", "本科", "2026", "1 年以上生产环境 Agent 开发经验",
     "招聘具备生产级 Agent 开发经验的工程师;注意:本岗位发布已超过有效期。",
     ["Python", "Agent 生产环境经验(1 年以上)", "LLM API", "React 基础"],
     ["生产级 Agent 开发", "Agent 稳定性保障"]),
    ("JD-030", "深圳市迟暮科技有限公司", "AI Agent 应用开发工程师(二次发布)", "深圳", False, "校招官网", "https://careers.example.com/jobs/jd-030",
     "2026-06-01", "2026-09-30", "AI Agent", "本科", "2026", "1 年以上生产环境 Agent 开发经验",
     "与 JD-029 为同一岗位的二次发布,岗位职责与要求一致。",
     ["Python", "Agent 生产环境经验(1 年以上)", "LLM API", "React 基础"],
     ["生产级 Agent 开发", "Agent 稳定性保障"]),
]


def main() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for row in JDS:
        (
            job_id, company, title, location, remote, source, url,
            posted_date, expires_at, job_type, degree_required,
            graduate_year_required, experience_required, jd_text,
            requirements, responsibilities,
        ) = row
        payload = {
            "job_id": job_id,
            "company": company,
            "title": title,
            "location": location,
            "remote": remote,
            "source": source,
            "url": url,
            "posted_date": posted_date,
            "expires_at": expires_at,
            "job_type": job_type,
            "degree_required": degree_required,
            "graduate_year_required": graduate_year_required,
            "experience_required": experience_required,
            "jd_text": jd_text,
            "requirements": requirements,
            "responsibilities": responsibilities,
        }
        path = JOBS_DIR / f"{job_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(job_id)
    print(f"wrote {len(written)} jobs to {JOBS_DIR}")


if __name__ == "__main__":
    main()

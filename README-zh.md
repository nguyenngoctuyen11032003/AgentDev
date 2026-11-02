# AgentDev

<p align="center">
  <img src="frontend/public/media/logo.svg" alt="AgentDev Logo" width="120"/>
</p>

<p align="center">
  <strong>用于开发一切的零代码多智能体平台</strong>
</p>

<p align="center">
  【<a href="./README.md">English</a> | <a href="./README-zh.md">简体中文</a>】
</p>
<p align="center">
    【📚 <a href="#开发者">开发者</a> | 👤 <a href="#作者">作者</a> | ⚖️ <a href="#许可证">许可证</a>】
</p>

## 📖 概览

**AgentDev** 是一个用于“开发一切”的**零代码多智能体平台**。它通过简单的配置，帮助用户快速构建并执行定制化的多智能体系统。无需编写代码，即可定义智能体、工作流和任务，以编排如数据可视化、3D 生成和深度调研等复杂场景。

AgentDev 由 [Nguyễn Ngọc Tuyền](https://github.com/nguyenngoctuyen11032003) 开发和维护，基于 OpenBMB 的 [ChatDev 2.0 (AgentDev)](https://github.com/OpenBMB/ChatDev)（Apache License 2.0）构建——详见[许可证与致谢](#许可证)。

## 🚀 快速开始

### 📋 环境要求

*   **操作系统**: macOS / Linux / WSL / Windows
*   **Python**: 3.12+
*   **Node.js**: 18+
*   **包管理器**: [uv](https://docs.astral.sh/uv/)

### 📦 安装

1.  **后端依赖**（由 `uv` 管理 Python）：
    ```bash
    uv sync
    ```

2.  **前端依赖**（Vite + Vue 3）：
    ```bash
    cd frontend && npm install
    ```

### ⚡️ 运行应用（本地）

#### 使用 Makefile（推荐）

**同时启动后端与前端**：
```bash
make dev
```

> 然后访问 Web 控制台：**[http://localhost:5173](http://localhost:5173)**。

#### 手动命令

1.  **启动后端**：
    ```bash
    # 从项目根目录运行
    uv run python server_main.py --port 6400 --reload
    ```
    > `--reload` 仅监听服务端 Python 源代码目录，`WareHouse/` 下的智能体生成文件不会再触发重启。可通过 `--reload-dir` / `--reload-exclude`（可多次指定）自定义。

2.  **启动前端**：
    ```bash
    cd frontend
    VITE_API_BASE_URL=http://localhost:6400 npm run dev
    ```
    > 然后访问 Web 控制台：**[http://localhost:5173](http://localhost:5173)**。

    > **💡 提示**：如果前端无法连接后端，可能是默认端口 `6400` 已被占用。
    > 请将前后端同时切换到一个空闲端口，例如：
    >
    > * **后端**：启动时指定 `--port 6401`
    > * **前端**：设置 `VITE_API_BASE_URL=http://localhost:6401`

#### 常用命令

*   **帮助命令**：
    ```bash
    make help
    ```

*   **同步 YAML 工作流到前端**：
    ```bash
    make sync
    ```
    将 `yaml_instance/` 中的所有工作流文件上传到数据库。

*   **校验所有 YAML 工作流**：
    ```bash
    make validate-yamls
    ```
    检查所有 YAML 文件的语法与 schema 错误。

### 🦞 使用 OpenClaw 运行

OpenClaw 可以与 AgentDev 集成，通过 **调用已有的 agent 团队**，或在 AgentDev 中 **动态创建新的 agent 团队** 来完成任务。

开始使用：

1. 启动 AgentDev 2.0 后端。
2. 为你的 OpenClaw 实例安装所需的技能：

    ```bash
    clawdhub install chatdev
    ```

3. 让 OpenClaw 创建一个 AgentDev 工作流。例如：

  * **自动化信息收集与内容发布**

    ```
    创建一个 AgentDev 工作流，用于自动收集热点信息，生成一篇小红书文案，并发布该内容
    ```

  * **多智能体地缘政治模拟**

    ```
    创建一个 AgentDev 工作流，构建多个 agent，用于模拟中东局势未来可能的发展
    ```


### 🐳 使用 Docker 运行
你也可以通过 Docker Compose 运行整个应用。该方式可简化依赖管理，并提供一致的运行环境。

1.  **前置条件**：
    *   已安装 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。
    *   请确保在项目根目录中存在用于配置 API Key 的 `.env` 文件。

2.  **构建并运行**：
    ```bash
    # 在项目根目录执行
    docker compose up --build
    ```

3.  **访问地址**：
    *   **后端**：`http://localhost:6400`
    *   **前端**：`http://localhost:5173`

> 服务在异常退出后会自动重启，本地文件的修改会同步映射到容器中，便于实时开发。

### 🔑 配置

*   **环境变量**：在项目根目录创建一个 `.env` 文件。
*   **模型密钥**：在 `.env` 中设置 `API_KEY` 和 `BASE_URL` 对应您的 LLM 提供商。
*   **YAML 占位符**：在配置文件中使用 `${VAR}`（如 `${API_KEY}`）来引用这些变量。

---

## 💡 如何使用

### 🖥️ Web 控制台

AgentDev 界面为构建和执行提供了无缝体验：

*   **教程 (Tutorial)**：平台内置了全面的分步指南和文档，帮助您快速上手。
*   **工作流 (Workflow)**：可视化画布，用于设计您的多智能体系统。通过轻松的拖拽来配置节点参数、定义上下文流并编排复杂的智能体交互。
*   **运行 (Launch)**：启动工作流、监控实时日志、检查中间产物，并提供人机协同反馈。

### 🧰 Python SDK
对于自动化和批量处理，使用我们轻量级的 Python SDK 编排任务并直接获取结果。

```python
from runtime.sdk import run_workflow

# 执行工作流并获取最后一条节点消息
result = run_workflow(
    yaml_file="yaml_instance/demo.yaml",
    task_prompt="用一句话总结附件文档。",
    attachments=["/path/to/document.pdf"],
    variables={"API_KEY": "sk-xxxx"} # 如果需要，可覆盖 .env 中的变量
)

if result.final_message:
    print(f"Output: {result.final_message.text_content()}")
```


---

<a id="开发者"></a>
## ⚙️ 给开发者

**如果您打算进行二次开发和扩展，请参阅本章节。**

您可以通过扩展节点、Provider 与工具来增强 AgentDev。
项目采用模块化结构：
*   **核心系统**：`server/` 承载 FastAPI 后端，`runtime/` 负责智能体抽象与工具执行。
*   **编排层**：`workflow/` 负责多智能体逻辑，配置位于 `entity/`。
*   **前端**：`frontend/` 是 Vue 3 Web 控制台。
*   **可扩展性**：`functions/` 用于自定义 Python 工具。

相关参考文档：
*   **快速开始**：[Start Guide](./docs/user_guide/zh/index.md)
*   **核心模块**：[Workflow Authoring](./docs/user_guide/zh/workflow_authoring.md)、[Memory](./docs/user_guide/zh/modules/memory.md) 和 [Tooling](./docs/user_guide/zh/modules/tooling/index.md)

---

## 🌟 推荐工作流
我们为常见场景提供了开箱即用的强大模板。所有可运行的工作流配置均位于 `yaml_instance/` 目录下。
*   **示例 (Demos)**：以 `demo_*.yaml` 命名的文件展示了特定功能或模块。
*   **实现 (Implementations)**：直接命名的文件（如 `AgentDev_v1.yaml`）是完整的自研或复刻流程。如下所示：

### 📋 工作流合集

| 类别 | 工作流                                                                                                         | 案例 | 
| :--- |:------------------------------------------------------------------------------------------------------------| :--- | 
| **📈 数据可视化** | `data_visualization_basic.yaml`<br>`data_visualization_enhanced.yaml`                                       | 提示词：*"Create 4–6 high-quality PNG charts for my large real-estate transactions dataset."* |
| **🛠️ 3D 场景生成**<br>*(需要 [Blender](https://www.blender.org/) 和 [blender-mcp](https://github.com/ahujasid/blender-mcp))* | `blender_3d_builder_simple.yaml`<br>`blender_3d_builder_hub.yaml`<br>`blender_scientific_illustration.yaml` | 提示词：*"Please build a Christmas tree."* |
| **🎮 游戏开发** | `GameDev_v1.yaml`<br>`AgentDev_v1.yaml`                                                                      | 提示词：*"Please help me design and develop a Tank Battle game."* |
| **📚 深度研究** | `deep_research_v1.yaml`                                                                                     | 提示词：*"Research about recent advances in the field of LLM-based agent RL"* |
| **🎓 教学视频** | `teach_video.yaml` (请在运行此工作流之前运行 `uv add manim` 命令)                                                         | 提示词：*"讲一下什么是凸优化"* |

------

### 💡 使用指南
对于这些实现，您可以使用 **Launch** 标签页来执行它们。
1.  **选择**：在 **Launch** 标签页选择一个工作流。
2.  **上传**：如果需要，上传相关文件（例如用于数据分析的 `.csv`）。
3.  **提示**：输入您的请求（例如*“可视化销售趋势”*或*“设计一个贪吃蛇游戏”*）。

---

## 🤝 参与贡献

欢迎任何形式的贡献！无论是修复 Bug、添加新的工作流模板，还是分享由 AgentDev 生成的优质案例，欢迎在 [nguyenngoctuyen11032003/AgentDev](https://github.com/nguyenngoctuyen11032003/AgentDev) 提交 **Issue** 或 **Pull Request**。请查看 [开发者指南](#开发者) 开始。

<a id="作者"></a>
## 👤 作者

**Nguyễn Ngọc Tuyền** — [@nguyenngoctuyen11032003](https://github.com/nguyenngoctuyen11032003)

<a id="许可证"></a>
## ⚖️ 许可证与致谢

Copyright © 2026 Nguyễn Ngọc Tuyền.

AgentDev 采用 [Apache License 2.0](./LICENSE) 许可。本项目是 [ChatDev](https://github.com/OpenBMB/ChatDev)（Copyright OpenBMB 及 ChatDev 贡献者，Apache-2.0）的衍生作品，原项目文件已被修改，详见 [NOTICE](./NOTICE)。

如在学术工作中使用相关研究，请引用 ChatDev 原始论文：

<details>
<summary>ChatDev 引用</summary>

```
@article{chatdev,
    title = {ChatDev: Communicative Agents for Software Development},
    author = {Chen Qian and Wei Liu and Hongzhang Liu and Nuo Chen and Yufan Dang and Jiahao Li and Cheng Yang and Weize Chen and Yusheng Su and Xin Cong and Juyuan Xu and Dahai Li and Zhiyuan Liu and Maosong Sun},
    journal = {arXiv preprint arXiv:2307.07924},
    url = {https://arxiv.org/abs/2307.07924},
    year = {2023}
}

@article{colearning,
    title = {Experiential Co-Learning of Software-Developing Agents},
    author = {Chen Qian and Yufan Dang and Jiahao Li and Wei Liu and Zihao Xie and Yifei Wang and Weize Chen and Cheng Yang and Xin Cong and Xiaoyin Che and Zhiyuan Liu and Maosong Sun},
    journal = {arXiv preprint arXiv:2312.17025},
    url = {https://arxiv.org/abs/2312.17025},
    year = {2023}
}

@article{macnet,
    title={Scaling Large-Language-Model-based Multi-Agent Collaboration},
    author={Chen Qian and Zihao Xie and Yifei Wang and Wei Liu and Yufan Dang and Zhuoyun Du and Weize Chen and Cheng Yang and Zhiyuan Liu and Maosong Sun}
    journal={arXiv preprint arXiv:2406.07155},
    url = {https://arxiv.org/abs/2406.07155},
    year={2024}
}

@article{iagents,
    title={Autonomous Agents for Collaborative Task under Information Asymmetry},
    author={Wei Liu and Chenxi Wang and Yifei Wang and Zihao Xie and Rennai Qiu and Yufan Dnag and Zhuoyun Du and Weize Chen and Cheng Yang and Chen Qian},
    journal={arXiv preprint arXiv:2406.14928},
    url = {https://arxiv.org/abs/2406.14928},
    year={2024}
}

@article{puppeteer,
      title={Multi-Agent Collaboration via Evolving Orchestration}, 
      author={Yufan Dang and Chen Qian and Xueheng Luo and Jingru Fan and Zihao Xie and Ruijie Shi and Weize Chen and Cheng Yang and Xiaoyin Che and Ye Tian and Xuantang Xiong and Lei Han and Zhiyuan Liu and Maosong Sun},
      journal={arXiv preprint arXiv:2505.19591},
      url={https://arxiv.org/abs/2505.19591},
      year={2025}
}
```

</details>

## 📬 联系方式

如有任何问题或反馈，请在 [nguyenngoctuyen11032003/AgentDev](https://github.com/nguyenngoctuyen11032003/AgentDev/issues) 提交 Issue。

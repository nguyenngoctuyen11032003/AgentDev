# AgentDev

<p align="center">
  <img src="frontend/public/media/logo.svg" alt="AgentDev Logo" width="120"/>
</p>

<p align="center">
  <strong>A Zero-Code Multi-Agent Platform for Developing Everything</strong>
</p>

<p align="center">
  【<a href="./README.md">English</a> | <a href="./README-zh.md">简体中文</a>】
</p>
<p align="center">
    【📚 <a href="#developers">Developers</a> | 👤 <a href="#author">Author</a> | ⚖️ <a href="#license">License</a>】
</p>

## 📖 Overview

**AgentDev** is a **Zero-Code Multi-Agent Platform** for "Developing Everything". It lets you rapidly build and run customized multi-agent systems through simple configuration. No coding is required—define agents, workflows, and tasks to orchestrate complex scenarios such as data visualization, 3D generation, and deep research.

AgentDev is developed and maintained by [Nguyễn Ngọc Tuyền](https://github.com/nguyenngoctuyen11032003). It is built on top of [ChatDev 2.0 (AgentDev)](https://github.com/OpenBMB/ChatDev) by OpenBMB, released under the Apache License 2.0 — see [License & Credits](#license).

## 📁 Project Structure

```
AgentDev/
├── backend/      # Python backend (uv project): main.py server, cli.py runner, agentdev/ package, scripts/, tests/
├── frontend/     # Vue 3 + Vite web console
├── workspace/    # user-editable content: workflows/, functions/, skills/, templates/, examples/
├── docs/         # user guide (en / zh)
├── storage/      # generated at runtime, gitignored: warehouse/ (session output), db/ (vuegraphs.db), logs/, temp/
├── compose.yml   # Docker Compose setup (backend + frontend)
└── Makefile      # dev shortcuts (make install / dev / help ...)
```

`.env` stays at the repository root. Set `AGENTDEV_STORAGE_DIR` to keep runtime data elsewhere (e.g. a mounted volume).

## 🚀 Quick Start

### 📋 Prerequisites

*   **OS**: macOS / Linux / WSL / Windows
*   **Python**: 3.12+
*   **Node.js**: 18+
*   **Package Manager**: [uv](https://docs.astral.sh/uv/)

### 📦 Installation

Install everything at once with `make install`, or step by step:

1.  **Backend Dependencies** (Python managed by `uv`):
    ```bash
    cd backend && uv sync
    ```

2.  **Frontend Dependencies** (Vite + Vue 3):
    ```bash
    cd frontend && npm install
    ```

### 🔑 Configuration

*   **Environment Variables**:
    ```bash
    cp .env.example .env
    ```
*   **Model Keys**: Set `API_KEY` and `BASE_URL` in `.env` for your LLM provider.
*   **YAML placeholders**: Use `${VAR}`（e.g., `${API_KEY}`）in configuration files to reference these variables.

### ⚡️ Run the Application

#### Using Makefile (Recommended)

**Start both Backend and Frontent**:
```bash
make dev
```

> Then access the Web Console at **[http://localhost:5173](http://localhost:5173)**.

#### Manual Commands

1.  **Start Backend**:
    ```bash
    # Run from the project root
    cd backend && uv run python main.py --port 6400 --reload
    ```
    > `--reload` watches the server's Python source folders only; agent-generated files under `storage/warehouse/` no longer trigger restarts. Pass `--reload-dir` or `--reload-exclude` (repeatable) to customise.

2.  **Start Frontend**:
    ```bash
    cd frontend
    VITE_API_BASE_URL=http://localhost:6400 npm run dev
    ```
    > Then access the Web Console at **[http://localhost:5173](http://localhost:5173)**. 
    
    
    > **💡 Tip**: If the frontend fails to connect to the backend, the default port `6400` may already be occupied.
    > Please switch both services to an available port, for example:
    >
    > * **Backend**: start with `--port 6401`
    > * **Frontend**: set `VITE_API_BASE_URL=http://localhost:6401`

#### Utility Commands

*   **Help command**:
    ```bash
    make help
    ```

*   **Sync YAML workflows to frontend**:
    ```bash
    make sync
    ```
    Uploads all workflow files from `workspace/workflows/` to the database.

*   **Validate all YAML workflows**:
    ```bash
    make validate-yamls
    ```
    Checks all YAML files for syntax and schema errors.

### 🦞 Run with OpenClaw
OpenClaw can integrate with AgentDev by invoking existing agent teams or dynamically creating new agent teams within AgentDev.
To get started:
1. Start the AgentDev 2.0 backend.
2. Install the required skills for your OpenClaw instance:
    ```bash
    clawdhub install chatdev
    ```

3. Ask your OpenClaw to create a AgentDev workflow. For example:

* **Automated information collection and content publishing**

  ```
  Create a AgentDev workflow to automatically collect trending information, generate a Xiaohongshu post, and publish it.
  ```

* **Multi-agent geopolitical simulation**
  ```
  Create a AgentDev workflow with multiple agents to simulate possible future developments of the Middle East situation.
  ```


### 🐳 Run with Docker
Alternatively, you can run the entire application using Docker Compose. This method simplifies dependency management and provides a consistent environment.

1.  **Prerequisites**:
    *   [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.
    *   Ensure you have a `.env` file in the project root for your API keys.

2.  **Build and Run**:
    ```bash
    # From the project root
    docker compose up --build
    ```

3.  **Access**:
    *   **Backend**: `http://localhost:6400`
    *   **Frontend**: `http://localhost:5173`

> The services will automatically restart if they crash, and local file changes will be reflected inside the containers for live development.

---

## 💡 How to Use

### 🖥️ Web Console

The AgentDev interface provides a seamless experience for both construction and execution

*   **Tutorial**: Comprehensive step-by-step guides and documentation integrated directly into the platform to help you get started quickly.
*   **Workflow**: A visual canvas to design your multi-agent systems. Configure node parameters, define context flows, and orchestrate complex agent interactions with drag-and-drop ease.
*   **Launch**: Initiate workflows, monitor real-time logs, inspect intermediate artifacts, and provide human-in-the-loop feedback.

### 🧰 Python SDK
For automation and batch processing, use our lightweight Python SDK to execute workflows programmatically and retrieve results directly.

```python
from agentdev.runtime.sdk import run_workflow

# Execute a workflow and get the final node message
result = run_workflow(
    yaml_file="workspace/workflows/demo.yaml",
    task_prompt="Summarize the attached document in one sentence.",
    attachments=["/path/to/document.pdf"],
    variables={"API_KEY": "sk-xxxx"} # Override .env variables if needed
)

if result.final_message:
    print(f"Output: {result.final_message.text_content()}")
```


---

<a id="developers"></a>
## ⚙️ For Developers

**For secondary development and extensions, please proceed with this section.**

Extend AgentDev with new nodes, providers, and tools.
The project is organized into a modular structure:

```
backend/                      # Python backend (uv project: pyproject.toml, uv.lock)
├── agentdev/                 #   single Python package
│   ├── entity/               #     workflow config dataclasses, messages, enums
│   ├── schema_registry/      #     node/edge/memory schema registrations
│   ├── runtime/              #     node & edge execution, agent providers, SDK
│   ├── workflow/             #     graph orchestration (DAG, cycles, executors)
│   ├── api/                  #     FastAPI app: routes/ + services/
│   ├── validation/           #     YAML/workflow validation (load_config)
│   ├── utils/                #     shared helpers (logging, attachments, paths)
│   └── paths.py              #     canonical repo locations
├── scripts/                  #   maintenance CLIs (cd backend && uv run python -m scripts.<name>)
├── tests/                    #   pytest suite
├── main.py                   #   HTTP server entry point
└── cli.py                    #   CLI workflow runner
workspace/                    # user-editable content
├── workflows/                #   workflow YAML definitions served by the API
├── functions/                #   user-extensible Python tools & edge functions
├── skills/                   #   agent skills
├── templates/                #   generated design template (design.yaml)
└── examples/                 #   sample MCP server
frontend/                     # Vue 3 web console (src/api, views, components, stores, i18n)
docs/                         # user guide
```

*   **Core Systems**: `backend/agentdev/api/` hosts the FastAPI backend, while `backend/agentdev/runtime/` manages agent abstraction and tool execution.
*   **Orchestration**: `backend/agentdev/workflow/` handles the multi-agent logic, driven by configurations in `backend/agentdev/entity/`.
*   **Frontend**: `frontend/` contains the Vue 3 Web Console.
*   **Extensibility**: `workspace/functions/` is the place for custom Python tools.

Relevant reference documentation:
*   **Getting Started**: [Start Guide](./docs/user_guide/en/index.md)
*   **Core Modules**: [Workflow Authoring](./docs/user_guide/en/workflow_authoring.md), [Memory](./docs/user_guide/en/modules/memory.md), and [Tooling](./docs/user_guide/en/modules/tooling/README.md)

---

## 🌟 Featured Workflows
We provide robust, out-of-the-box templates for common scenarios. All runnable workflow configs are located in `workspace/workflows/`.
*   **Demos**: Files named `demo_*.yaml` showcase specific features or modules.
*   **Implementations**: Files named directly (e.g., `AgentDev_v1.yaml`) are full in-house or recreated workflows. As follows:

### 📋 Workflow Collection

| Category | Workflow                                                                                                    | Case | 
| :--- |:------------------------------------------------------------------------------------------------------------| :--- | 
| **📈 Data Visualization** | `data_visualization_basic.yaml`<br>`data_visualization_enhanced.yaml`                                       | Prompt: *"Create 4–6 high-quality PNG charts for my large real-estate transactions dataset."* |
| **🛠️ 3D Generation**<br>*(Requires [Blender](https://www.blender.org/) & [blender-mcp](https://github.com/ahujasid/blender-mcp))* | `blender_3d_builder_simple.yaml`<br>`blender_3d_builder_hub.yaml`<br>`blender_scientific_illustration.yaml` | Prompt: *"Please build a Christmas tree."* |
| **🎮 Game Dev** | `GameDev_v1.yaml`<br>`AgentDev_v1.yaml`                                                                      | Prompt: *"Please help me design and develop a Tank Battle game."* |
| **📚 Deep Research** | `deep_research_v1.yaml`                                                                                     | Prompt: *"Research about recent advances in the field of LLM-based agent RL"* |
| **🎓 Teach Video** | `teach_video.yaml` (Please run command `cd backend && uv add manim` before running this workflow)                         | Prompt: *"讲一下什么是凸优化"* |

---

### 💡 Usage Guide
For those implementations, you can use the **Launch** tab to execute them.
1.  **Select**: Choose a workflow in the **Launch** tab.
2.  **Upload**: Upload necessary files (e.g., `.csv` for data analysis) if required.
3.  **Prompt**: Enter your request (e.g., *"Visualize the sales trends"* or *"Design a snake game"*).

---

## 🤝 Contributing

Contributions are welcome! Whether you're fixing bugs, adding new workflow templates, or sharing high-quality cases produced by AgentDev, feel free to open an **Issue** or **Pull Request** at [nguyenngoctuyen11032003/AgentDev](https://github.com/nguyenngoctuyen11032003/AgentDev). Check out the [Developer Guide](#developers) to get started.

<a id="author"></a>
## 👤 Author

**Nguyễn Ngọc Tuyền** — [@nguyenngoctuyen11032003](https://github.com/nguyenngoctuyen11032003)

<a id="license"></a>
## ⚖️ License & Credits

Copyright © 2026 Nguyễn Ngọc Tuyền.

AgentDev is licensed under the [Apache License 2.0](./LICENSE). It is a derivative work of [ChatDev](https://github.com/OpenBMB/ChatDev) (Copyright OpenBMB and the ChatDev contributors), also licensed under Apache-2.0. Files from the original project have been modified; see [NOTICE](./NOTICE) for details.

If you use the underlying research in academic work, please cite the original ChatDev papers:

<details>
<summary>ChatDev citations</summary>

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

## 📬 Contact

For questions or feedback, please open an issue at [nguyenngoctuyen11032003/AgentDev](https://github.com/nguyenngoctuyen11032003/AgentDev/issues).

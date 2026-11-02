from fastapi import FastAPI
from agentdev.server.bootstrap import init_app
from agentdev.utils.env_loader import load_dotenv_file

load_dotenv_file()

app = FastAPI(title="AgentDev Workflow Server", version="1.0.0")
init_app(app)

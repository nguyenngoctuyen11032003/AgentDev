from fastapi import FastAPI
from agentdev.api.bootstrap import init_app
from agentdev.utils.env_loader import load_dotenv_file

load_dotenv_file()

# Runs started by the server without a live chat (sync API, batch) must never block on input() in
# the server console when a workflow asks the user something; they get an automatic answer instead.
import os as _os
_os.environ.setdefault("AGENTDEV_NONINTERACTIVE", "1")

app = FastAPI(title="AgentDev Workflow Server", version="1.0.0")
init_app(app)

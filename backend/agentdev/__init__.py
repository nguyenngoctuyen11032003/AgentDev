"""AgentDev backend: workflow configuration, runtime, orchestration and HTTP server."""

# Importing ``paths`` puts ``workspace/`` on ``sys.path`` so user functions can
# import each other as ``functions.*`` regardless of the working directory.
from agentdev import paths as _paths  # noqa: F401

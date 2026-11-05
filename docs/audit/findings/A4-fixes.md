# A4 fixes (Connections backend)

| id | status | test file |
|---|---|---|
| A4-1 | fixed: same-vendor account wins over default; default preferred among same vendor; log names the real connection | tests/test_connection_autobind.py, tests/test_default_connection.py (locking test changed deliberately) |
| A4-2 | fixed backend: DELETE signs CLI out only with ?sign_out_cli=true (default false) and never while another connection shares the login; frontend checkbox/toast belongs to the UI owner | tests/test_connections.py |
| A4-3 | fixed: model swapped only when provider is set and vendor differs | tests/test_connection_autobind.py |
| A4-4 | fixed: CliLoginManager.shutdown() called from lifespan in api/bootstrap.py | tests/test_cli_login.py |
| A4-5..A4-9 | skipped: P3 or SUSPECTED (A4-6 in workflow_lab.py, owned by Lab owner) | - |

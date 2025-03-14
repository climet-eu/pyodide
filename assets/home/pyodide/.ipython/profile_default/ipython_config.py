import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "startup_extensions"))

c.InteractiveShellApp.reraise_ipython_extension_failures = True
c.InteractiveShellApp.extensions.append("climet_lab_bootstrap")

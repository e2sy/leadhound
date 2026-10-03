"""PyInstaller entry point — absolute imports only, safe when frozen.

The package's __main__.py uses relative imports (python -m leadhound
semantics), which break under PyInstaller. This script is the build target.
"""

from leadhound.cli import main

if __name__ == "__main__":
    main()

"""Provide Hook implementations for boardfarm plugins.

Hooks may be implemented per functionality, for example
- contingency checks
- environment checks
- service configurations
"""

import pluggy

# hook implementation for contingency checks
hookimpl = pluggy.HookimplMarker("boardfarm")

# hook implementation for service checks within contingency check
contingency_impl = pluggy.HookimplMarker("contingency")

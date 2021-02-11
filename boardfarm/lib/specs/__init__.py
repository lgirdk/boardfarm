"""Provide Hook specifications for boardfarm plugins.

Allow specs per functionality, for example
- contingency checks
- environment checks
- service configurations
"""

import pluggy

# hook spec for contingency checks
hookspec = pluggy.HookspecMarker("boardfarm")

# hook spec for service checks within contingency check
contingency_spec = pluggy.HookspecMarker("contingency")

# Overlays

Boardfarm follows the following overlay:

```
├── boardfarm
|   ├── configs
|   │   ├── mibs
|   │   │   ├── **/*.mib
|   ├── devices
|   │   ├── base_devices
|   │   │   ├── **/*.py
|   │   ├── demo_devices
|   │   │   ├── **/*.py
|   │   ├── **/*.py
|   ├── docs
|   │   ├── Explanation
|   │   │   ├── **/*.md
|   │   ├── How to guides
|   │   │   ├── **/*.md
|   │   ├── Reference
|   │   │   ├── **/*.md
|   │   ├── Tutorials
|   │   │   ├── **/*.md
|   ├── lib
|   │   ├── connections
|   │   │   ├── **/*.py
|   │   ├── parsers
|   │   │   ├── **/*.py
|   │   ├── **/*.py
|   ├── plugins
|   │   ├── hookspecs
|   │   │   ├── **/*.py
|   │   ├── **/*.py
|   |── templates
|   │   ├── **/*.py
|   ├── use_cases
|   │   ├── **/*.py
|   ├── exceptions.py
├── unittests
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── LICENSE
├── noxfile.py
├── pyproject.toml
└── .gitignore
```

# Installation

Follow the below steps to install Boardfarm

- Clone Boardfarm repositary

```bash
git clone
```

- Create a virtual environment

```bash
mkdir -p ~/<workspace>/
python -m venv ~/<workspace>/<venv_name>
cd <workspace>
. <venv_name>/bin/activate
```

- Install Boardfarm as an editable package

```bash
pip install -e boardfarm[doc,dev,test]
```

- Confirm installation worked

```bash
boardfarm --help
```

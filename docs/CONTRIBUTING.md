## Getting Started
Contributions are made to this repo via Issues and Pull Requests (PRs). A few general guidelines that cover both:
- Search for existing Issues and PRs before creating your own.

### Issues
Issues should be used to report problems with the package or discuss potential changes before a PR is created. Create a 
new Issue using [templates](https://github.com/DynamicalSystemsGroup/cats/issues/new/choose) to guide you through collecting and 
providing the information we need to investigate.

If you find an Issue that addresses the problem you're having, please add your own reproduction information to the 
existing issue rather than creating a new one.

### Pull Requests
Pull-requests (PRs) will be made using a PR [template](../.github/PULL_REQUEST_TEMPLATE/pull_request_template.md) 
(loaded automatically when a PR is created). PRs will reference issues that will include your fix or improvement slated 
for the next release:
- Only fix/add the functionality in question.
- Include documentation in the repo if applicable.

In general, we follow the ["fork-and-pull"](https://github.com/susam/gitpr) Git workflow.

1. Fork the repository to your own Github account
2. Clone the project to your machine
3. Create a new branch from the `release` branch locally with a succinct but descriptive name
4. Set up your environment with [uv](https://docs.astral.sh/uv/) and commit changes to the new branch:
   ```bash
   uv sync --extra ops --group dev   # for the MAC experiment, also: uv pip install -r experiments/mac/requirements-mac.txt
   uv run pytest -s tests/test_provenance.py
   ```
   If you add, remove, or bump a dependency in `pyproject.toml`, run `uv lock` and commit the updated
   `uv.lock` alongside your change so the lockfile stays reproducible for other contributors and CI.
5. Following any formatting and testing guidelines specific to this repo
6. Push changes to your fork
7. Open a PR in our repository and follow the PR template so that we can efficiently review the changes.
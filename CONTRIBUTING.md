# Scenario IFSEI Interface

[![Tests](https://github.com/carlosmazzei/pyscenario/actions/workflows/cicd.yaml/badge.svg)](https://github.com/carlosmazzei/pyscenario/actions/workflows/cicd.yaml)
[![codecov](https://codecov.io/gh/carlosmazzei/pyscenario/branch/master/graph/badge.svg)](https://codecov.io/gh/carlosmazzei/pyscenario)
[![PyPI version](https://badge.fury.io/py/pyscenario.svg)](https://pypi.org/project/pyscenario/)
[![Documentation Status](https://readthedocs.org/projects/pyscenario/badge/?version=latest)](https://pyscenario.readthedocs.io/en/latest/?badge=latest)

Python Scenario Automation contains a library to interface with Scenario IFSEI Classic for home automation.

Original repository: [https://github.com/carlosmazzei/pyscenario](https://github.com/carlosmazzei/pyscenario)

## Code of Conduct

Everyone participating in the community, and in particular in our
issue tracker, pull requests, and chat, is expected to treat
other people with respect and more generally to follow the guidelines
articulated in the [Python Community Code of Conduct](https://www.python.org/psf/codeofconduct/).

## Linting and Testing

### Locally on every commit

On every commit, some code formatting and checking tools are run by
[pre-commit](https://pre-commit.com/).

The test pipeline is configured in the
[.pre-commit-config.yaml](.pre-commit-config.yaml).

**Note:** you *must* run `poetry run pre-commit install` everytime you clone your
git repository. Else, the pre-commit hooks won't be run automatically.

### Running tests locally

On your local machine, you can run tests by running `make test`.

This uses [Tox](https://tox.wiki/en/latest/) to run tests for a variety
of Python versions.

As a prerequisite you need to install all those Python version, e.g., with
[pyenv](https://github.com/pyenv/pyenv).

To configure the Python versions under test, edit the [tox.ini](tox.ini).

## With Github actions

After every push to Github, the [cicd.yaml](.github/workflows/cicd.yaml)
workflow is run. It runs the tests in the [tests](tests) folder.

It also uploads the code coverage report to [codecov](https://codecov.io).

**Note:** for private repositories you need to acquire a token from codecov
and configure in the `cicd.yaml` workflow file and in Github secrets.

To configure which Python versions are tested, edit the `python-version`
list in the `cicd.yaml` workflow file.

## How to release to PyPI

You can upload the package either from your local machine via twine, or
by using Github actions.

The following instructions guide you through the process of releasing to the actual,
official PyPI.

Further down, there are instructions to release to the PyPI test server, or to custom
Python Package indexes.

### Release with Github actions

To make a release via Github actions, you need to create a release in
Github. When the release is published, the build-n-publish job in the
[cicd](.github/workflows/cicd.yaml) workflow
is run.

To create a release in Github you need to create a tag.

For this project it is necessary that the tag matches the version number.
E.g., for version `1.2.3` the tag must be `1.2.3`.

#### Prerequisites

1. Create an API token in the
   [PyPI account settings](https://pypi.org/manage/account/).
   If you don't have a PyPI account yet, create one. *Do not close the
   page right away, you will never see the token again!*

   **Note:** before you upload the package for the first time, you can
   only create a global api token with access to all your packages. It is
   *highly* recommended to replace it with a package-specific token after
   you have published your package for the first time.
2. In the [Github repository settings](https://github.com/carlosmazzei/pyscenario/settings/environments),
   create a new environment named `production`. If you are the only
   contributor, you can leave all settings at the default.
3. Under [Secrets -> actions](https://github.com/carlosmazzei/pyscenario/settings/secrets/actions),
   create a new secret named `PYPI_API_TOKEN` and copy the token from PyPI
   as value.

#### Create a release and publish the package to PyPI

1. Make sure the `name` variable in your [pyproject.toml](pyproject.toml) is correct.
   **This will be the name of your package on PyPI!**
2. update the version number in the [pyproject.toml](pyproject.toml).
3. create a matching tag on your local machine and push it to the
   Github repository:

   ```bash
   git tag 1.2.3
   git push --tags
   ```

4. In [Github actions](https://github.com/carlosmazzei/pyscenario/actions)
   make sure that the test workflow succeeds.
5. In the Github [release tab](https://github.com/carlosmazzei/pyscenario/releases)
   click "Draft a new release". Fill in the form. When you click publish,
   the `publish-to-pypi` workflow is run.

   It checks that the tag matches the version number and then builds and
   publishes the package to
   [PyPI](https://pypi.org/project/pyscenario/).

### Upload from the local machine (not recommended)

[twine](https://twine.readthedocs.io/en/stable/) allows to upload a package
from your local machine to PyPI.

#### Prerequisites for local machine

You need a PyPI API token. See prerequisites for the Github actions above
(you don't need to perform any actions on Github when using twine, so you
only need to perform step 1).

#### Configuration

The PyPI credentials must be configured either via a configuration file
or via environment variables.
See the [twine documentation](https://twine.readthedocs.io/en/stable/#configuration)
for details.

Since we are using an api token to authenticate with PyPI, the username
must be set to `__token__`, and the password is the actual token.

When using the PyPI test server, the repository url must be set to
`https://test.pypi.org/legacy/`.

#### Usage

The `publish` target in the [Makefile](Makefile) calls twine to upload
a package to PyPI.

**Note:** the upload command is deactivated by default to prevent accidental
uploads. You need to manually uncomment it before the first release.

Here are the necessary steps:

1. update the version number in the [pyproject.toml](pyproject.toml)
2. run `make publish`.

## Using a custom package repository

While testing the release process of a public package, it is a good idea to first
release to the PyPI Test server.

Sometimes, especially in corporate settings, it is necessary to upload packages to
a custom, often private, package repository.

### Releasing

To release to a server other than the standard PyPI, you need to specify the respective
repository URL when uploading.

#### Releasing to a custom repo with twine

With twine, you can specify the repository URL via the `--repository-url` parameter.

In the special case of the PyPI Test server, you can also specify
`--repository testpypi`.

```bash
# for Test PyPI
twine upload --repository testpypi dist/*

# for any custom repository
twine upload --repository-url <URL> dist/*
```

In the context of this project, you can modify the `publish` target in the
[Makefile](Makefile).

See also [Using TestPyPI](https://packaging.python.org/en/latest/guides/using-testpypi/).

#### Releasing to a custom repo with Github actions

To release to a custom repo with Github actions, you can follow the same process
as described above for the default PyPI. The only necessary change is adding a
`repository_url` entry to the `publish-to-pypi.yaml` file:

```yaml
- name: Publish package to TestPyPI
  uses: pypa/gh-action-pypi-publish@release/v1
  with:
    user: __token__password: ${{ secrets.TEST_PYPI_API_TOKEN }}repository_url: https://test.pypi.org/legacy/
```

For use with Test PyPI you need an account and an API token from [test.pypi.org](https://test.pypi.org). Note that in the example above, that token is assumed to
be stored in the `TEST_PYPI_API_TOKEN` secret in Github.

See also [Advanced release management](https://github.com/marketplace/actions/pypi-publish#advanced-release-management)
in the documentation of the `pypi-publish` Github action.

### Installing from a custom package repository

If you have uploaded your package to a custom repository, install tools such as
pip and poetry won't find it by default. You need to configure them to use the
custom repository.

#### Installing from a custom package repository with pip

With pip, you need to specify it via the `--index-url` parameter. Often you want to
install custom packages from the private repo, but public dependencies from the regular
PyPI. In that case, specify the PyPI repo via `--extra-index-url`.

For example:

`pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ pyscenario`

**Beware the
[security implications](https://medium.com/@alex.birsan/dependency-confusion-4a5d60fec610)!**

#### Installing from a custom package repository with poetry

To install packages from a custom repository, add this to your `pyproject.toml`:

```toml
[[tool.poetry.source]]
name = "foo"
url = "https://test.pypi.org/simple/"
secondary = true  # if True, poetry will also search the default PyPI repository
default = true  # if True, poetry will never search the default PyPI repository
```

For advanced configuration and authentication, take a look at the
[poetry documentation](https://python-poetry.org/docs/repositories/#install-dependencies-from-a-private-repository).

## Contact

Carlos Mazzei
  ([carlos.mazzei@gmail.com](mailto:carlos.mazzei@gmail.com))

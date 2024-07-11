# Contributing to Scenario

Python Scenario Automation contains a library to interface with Scenario IFSEI Classic for home automation. If you want to contribute and extend functionalities, feel free to do so.

## Code of Conduct

Everyone participating in the community, and in particular in our issue tracker, pull requests, and chat, is expected to treat other people with respect and more generally to follow the guidelines articulated in the [Python Community Code of Conduct](https://www.python.org/psf/codeofconduct/).

## Getting started with development

### Setup

#### (1) Fork the pyscenario repository

Within Github, navigate to <https://github.com/carlosmazzei/pyscenario> and fork the repository.

#### (2) Clone the pyscenario repository and enter into it

```bash
git clone git@github.com:<your_username>/pyscenario.git
cd pyscenario
```

#### (3) Install the test requirements and the project

```bash
make install
```

> **Note**
> You'll need Python 3.12 or higher to install all requirements

## Linting and Testing

### Locally on every commit

On every commit, some code formatting and checking tools are run by
[pre-commit](https://pre-commit.com/).

The test pipeline is configured in the
[.pre-commit-config.yaml](.pre-commit-config.yaml).

> **Note:** you *must* run `poetry run pre-commit install` everytime you clone your git repository. Else, the pre-commit hooks won't
> be run automatically.

### Running tests locally

On your local machine, you can run tests by running `make test`.

This uses [Tox](https://tox.wiki/en/latest/) to run tests for a variety of Python versions.

As a prerequisite you need to install all those Python version, e.g., with
[pyenv](https://github.com/pyenv/pyenv).

To configure the Python versions under test, edit the [tox.ini](tox.ini).

### With Github actions

After every push to Github, the [cicd.yaml](.github/workflows/cicd.yaml) workflow is run. It runs the tests in the [tests](tests) folder.

It also uploads the code coverage report to [codecov](https://codecov.io).

## How to release to PyPI

You can upload the package by using Github actions.

The following instructions guide you through the process of releasing to the actual, official PyPI.

Further down, there are instructions to release to the PyPI test server, or to custom Python Package indexes.

### Release with Github actions

To make a release via Github actions, you need to create a release in Github. When the release is published, the build-n-publish job in the [cicd](.github/workflows/cicd.yaml) workflow is run.

To create a release in Github you need to create a tag.

For this project it is necessary that the tag matches the version number.
E.g., for version `1.2.3` the tag must be `1.2.3`.

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

## Using a custom package repository

While testing the release process of a public package, it is a good idea to first release to the PyPI Test server.

### Releasing

To release to a server other than the standard PyPI, you need to specify the respective repository URL when uploading.

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

To release to a custom repo with Github actions, you can follow the same process as described above for the default PyPI. The only necessary change is adding a `repository_url` entry to the `publish-to-pypi.yaml` file:

```yaml
- name: Publish package to TestPyPI
  uses: pypa/gh-action-pypi-publish@release/v1
  with:
    user: __token__password: ${{ secrets.TEST_PYPI_API_TOKEN }}repository_url: https://test.pypi.org/legacy/
```

For use with Test PyPI you need an account and an API token from [test.pypi.org](https://test.pypi.org). Note that in the example above, that token is assumed to be stored in the `TEST_PYPI_API_TOKEN` secret in Github.

See also [Advanced release management](https://github.com/marketplace/actions/pypi-publish#advanced-release-management)
in the documentation of the `pypi-publish` Github action.

## Contact

Carlos Mazzei
  ([carlos.mazzei@gmail.com](mailto:carlos.mazzei@gmail.com))

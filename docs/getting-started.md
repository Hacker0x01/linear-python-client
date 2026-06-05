# Getting started

## Install

The package is distributed as assets on its
[GitHub Releases](https://github.com/Hacker0x01/linear-python/releases) (not on
PyPI):

```sh
# from a release wheel
uv pip install https://github.com/Hacker0x01/linear-python/releases/download/v0.1.0/linear_python-0.1.0-py3-none-any.whl

# or from a tag (builds from source)
uv pip install "git+https://github.com/Hacker0x01/linear-python@v0.1.0"
```

Or, working inside a clone of the repository:

```sh
uv sync
```

The package requires **Python 3.14+** and depends on
[`httpx`](https://www.python-httpx.org/) and
[`pydantic`](https://docs.pydantic.dev/).

## Get a token

You can authenticate in two ways:

- **Personal API key** — create one in Linear under
  *Settings → Security & access → Personal API keys*. Best for scripts and internal
  tooling.
- **OAuth 2.0 access token** — for applications acting on behalf of other users. See
  the [Linear OAuth docs](https://linear.app/developers).

## Create a client

=== "API key"

    ```python
    from linear_python import LinearClient

    client = LinearClient(api_key="lin_api_...")
    ```

=== "OAuth token"

    ```python
    from linear_python import LinearClient

    client = LinearClient(access_token="...")
    ```

=== "From the environment"

    ```python
    # Reads LINEAR_API_KEY from the environment.
    from linear_python import LinearClient

    client = LinearClient()
    ```

Prefer the context-manager form so the underlying HTTP connection is closed for you:

```python
with LinearClient() as client:
    print(client.viewer().viewer.name)
```

## Make your first call

Every method takes a typed `*Request` and returns a typed `*Response`. `viewer()`
takes no input, so it's the simplest call — its response exposes `.viewer`:

```python
with LinearClient() as client:
    me = client.viewer().viewer
    print(me.id, me.name, me.email)
```

If the credentials are wrong you'll get a
[`LinearAuthenticationError`][linear_python.LinearAuthenticationError]. See
[Error handling](usage.md#error-handling) for the full list.

Next: the [Usage guide](usage.md).

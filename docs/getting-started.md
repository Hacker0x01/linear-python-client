# Getting started

## Install

```sh
uv add linear-python-client
# or
pip install linear-python-client
```

Or, working inside a clone of the repository:

```sh
uv sync
```

The package requires **Python 3.13+** and depends on
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
    from linear_python_client import LinearClient

    client = LinearClient(api_key="lin_api_...")
    ```

=== "OAuth token"

    ```python
    from linear_python_client import LinearClient

    client = LinearClient(access_token="...")
    ```

=== "From the environment"

    ```python
    # Reads LINEAR_API_KEY from the environment.
    from linear_python_client import LinearClient

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
[`LinearAuthenticationError`][linear_python_client.LinearAuthenticationError]. See
[Error handling](usage.md#error-handling) for the full list.

Next: the [Usage guide](usage.md).
